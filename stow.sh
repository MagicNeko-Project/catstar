#!/usr/bin/env bash
#
# This script manages symlinks that link configuration files under 'src/' to the target system (e.g., /usr/local).
# It allows you to safely deploy, remove, or inspect active symlinks.
#

set -euo pipefail

# Color codes for premium CLI formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Determine repository base directory
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TARGET="/usr/local"
TARGET_DIR="$DEFAULT_TARGET"

# Command and options defaults
COMMAND="deploy"
DRY_RUN=false

# The base subdirectories to pre-create for all target environments to prevent directory folding
BASE_REQUIRED_SUBDIRECTORIES=(
    "bin"
    "etc"
    "etc/nftables.d"
    "share/zsh"
)

# The system-level subdirectories to pre-create only on standard system targets
SYSTEM_REQUIRED_SUBDIRECTORIES=(
    "lib/systemd/system"
    "lib/systemd/user"
)

# Target environment classification flags
IS_SYSTEM_TARGET=false
IS_USER_TARGET=false

# Active subdirectories and ignore patterns (determined dynamically at startup)
ACTIVE_REQUIRED_SUBDIRECTORIES=()
ACTIVE_IGNORE_PATTERNS=()

# Subdirectories exclusively owned by us that should be folded on all targets
EXCLUSIVE_FOLDED_SUBDIRECTORIES=(
    "share/zsh/catstar"
    "share/zsh/catstar/functions"
)


show_usage() {
    echo -e "$(cat << EOF
${CYAN}Symlink Deployment Manager${NC}

This utility manages symlinks that link configuration files under 'src/' to a target directory (e.g., /usr/local).

${YELLOW}Result of Running This Script:${NC}
  Replicates the 'src/' folder structure into the target system directory as active symlinks.
  This allows files inside your local Git repository to be live-active on the system. Any local edits to the repo
  take effect instantly on the system without manual copying, while keeping the system clean and allowing easy removal.

${YELLOW}Usage:${NC}
  stow.sh [command] [options]

${YELLOW}Commands:${NC}
  deploy     Create or update all configuration symlinks from 'src/' to target system (Default)
  undeploy   Remove all configuration symlinks from target system
  status     Inspect and list currently active symlinks and highlight any broken/dead links

${YELLOW}Options:${NC}
  -t, --target <dir>  Override the target system directory (Default: /usr/local)
  -d, --dry-run       Simulate deployment/removal showing planned filesystem changes
  -h, --help          Show this help menu

${YELLOW}Examples:${NC}
  stow.sh deploy
  stow.sh status --target ~/.local
  stow.sh undeploy --dry-run
EOF
)"
}


# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        deploy|undeploy|status)
            COMMAND="$1"
            shift
            ;;
        -t|--target)
            if [[ -z "${2:-}" ]]; then
                echo -e "${RED}Error: --target requires an argument.${NC}" >&2
                exit 1
            fi
            TARGET_DIR="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option '$1'.${NC}" >&2
            show_usage
            exit 1
            ;;
    esac
done

# Determine target classification
IS_SYSTEM_TARGET=false
if [[ "$TARGET_DIR" == "/usr/local" || "$TARGET_DIR" == "/usr" || "$TARGET_DIR" == "/" ]]; then
    IS_SYSTEM_TARGET=true
fi

IS_USER_TARGET=false
if [[ "$TARGET_DIR" == */.local || "$TARGET_DIR" == */.local/ ]]; then
    IS_USER_TARGET=true
fi

# Build active directory pre-creation and ignore arrays dynamically
ACTIVE_REQUIRED_SUBDIRECTORIES=("${BASE_REQUIRED_SUBDIRECTORIES[@]}")
ACTIVE_IGNORE_PATTERNS=()

if [[ "$IS_SYSTEM_TARGET" == "true" ]]; then
    ACTIVE_REQUIRED_SUBDIRECTORIES+=("${SYSTEM_REQUIRED_SUBDIRECTORIES[@]}")
elif [[ "$IS_USER_TARGET" == "true" ]]; then
    ACTIVE_REQUIRED_SUBDIRECTORIES+=("lib/systemd/user")
    ACTIVE_IGNORE_PATTERNS+=("lib/systemd/system")
else
    # Non-standard target: ignore the entire systemd folder tree
    ACTIVE_IGNORE_PATTERNS+=("lib/systemd")
fi


# Verify write permissions for the target directory
check_permissions() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    if [[ ! -w "$TARGET_DIR" ]]; then
        echo -e "${RED}Error: Target directory '$TARGET_DIR' is not writable by the current user.${NC}" >&2
        echo -e "${RED}Please run this script with root privileges (e.g., sudo ./stow.sh).${NC}" >&2
        exit 4
    fi
}


ensure_target_directories() {
    echo -e "${BLUE}Ensuring target subdirectories exist in '$TARGET_DIR'...${NC}"
    for subdir in "${ACTIVE_REQUIRED_SUBDIRECTORIES[@]}"; do
        local full_path="$TARGET_DIR/$subdir"
        if [[ ! -d "$full_path" ]]; then
            if [[ "$DRY_RUN" == "true" ]]; then
                echo -e "${CYAN}[Dry-Run] Would create directory: $full_path${NC}"
            else
                echo -e "  Creating directory: $full_path"
                mkdir -p "$full_path"
            fi
        fi
    done
}


check_conflicts() {
    echo -e "${BLUE}Checking for conflicts in '$TARGET_DIR'...${NC}"
    local conflicts_found=0
    local -A checked_paths=()

    # We scan 'src' to find target destinations that already exist as regular files
    while IFS= read -r -d '' file; do
        local rel_path="${file#$BASE_DIR/src/}"

        # Skip conflict checks for active ignore patterns
        local skip=false
        for pattern in "${ACTIVE_IGNORE_PATTERNS[@]}"; do
            if [[ "$rel_path" == "$pattern" || "$rel_path" == "$pattern"/* ]]; then
                skip=true
                break
            fi
        done
        if [[ "$skip" == "true" ]]; then
            continue
        fi

        # Fold checks to the custom folder level if inside an exclusive folded directory (matches shallowest first)
        for exclusive in "${EXCLUSIVE_FOLDED_SUBDIRECTORIES[@]}"; do
            if [[ "$rel_path" == "$exclusive" || "$rel_path" == "$exclusive"/* ]]; then
                rel_path="$exclusive"
                break
            fi
        done

        # De-duplicate checks since multiple nested files map to the same folded parent
        if [[ -n "${checked_paths[$rel_path]:-}" ]]; then
            continue
        fi
        checked_paths[$rel_path]=1

        local dest_path="$TARGET_DIR/$rel_path"

        if [[ -e "$dest_path" && ! -L "$dest_path" ]]; then
            echo -e "${RED}Conflict detected: Regular file or directory exists at destination: $dest_path${NC}" >&2
            conflicts_found=1
        fi
    done < <(find "$BASE_DIR/src" -type f -print0)

    if [[ "$conflicts_found" -ne 0 ]]; then
        echo -e "${RED}Error: Conflicts detected. Please resolve them before deploying.${NC}" >&2
        exit 2
    fi
    echo -e "${GREEN}No conflicts detected.${NC}"
}


clean_unfolded_exclusive_directories() {
    for (( i=${#EXCLUSIVE_FOLDED_SUBDIRECTORIES[@]}-1; i>=0; i-- )); do
        local subdir="${EXCLUSIVE_FOLDED_SUBDIRECTORIES[i]}"
        local full_path="$TARGET_DIR/$subdir"

        # Skip if any parent of this exclusive directory is already folded (a symlink)
        local parent_is_folded=false
        for parent_dir in "${EXCLUSIVE_FOLDED_SUBDIRECTORIES[@]}"; do
            if [[ "$subdir" == "$parent_dir"/* && -L "$TARGET_DIR/$parent_dir" ]]; then
                parent_is_folded=true
                break
            fi
        done

        if [[ "$parent_is_folded" == "true" ]]; then
            continue
        fi

        # If it exists and is a real folder (not a symlink), clean it up
        if [[ -d "$full_path" && ! -L "$full_path" ]]; then
            echo -e "${YELLOW}Migration: Found unfolded exclusive directory: $full_path${NC}"
            echo -e "  Unstowing existing links to clean target directory..."

            local stow_flags=("-t" "$TARGET_DIR" "-d" "$BASE_DIR" "-D" "src")
            for pattern in "${ACTIVE_IGNORE_PATTERNS[@]}"; do
                stow_flags+=("--ignore=$pattern")
            done

            # Run unstow silently
            stow "${stow_flags[@]}" 2>/dev/null || true

            # Delete the directory only if it is now empty
            if [[ -z "$(find "$full_path" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
                if [[ "$DRY_RUN" == "true" ]]; then
                    echo -e "${CYAN}[Dry-Run] Would remove empty unfolded exclusive directory: $full_path${NC}"
                else
                    echo -e "  Removing empty directory to allow Stow folding: $full_path"
                    rm -rf "$full_path"
                fi
            else
                echo -e "${RED}Warning: Directory '$full_path' is not empty. Skipping removal to prevent data loss.${NC}" >&2
            fi
        fi
    done
}


execute_deploy() {
    check_permissions
    ensure_target_directories
    clean_unfolded_exclusive_directories
    check_conflicts

    echo -e "${BLUE}Creating symlinks...${NC}"

    local stow_flags=("-t" "$TARGET_DIR" "-d" "$BASE_DIR" "-R" "src")

    for pattern in "${ACTIVE_IGNORE_PATTERNS[@]}"; do
        stow_flags+=("--ignore=$pattern")
    done

    if [[ "$DRY_RUN" == "true" ]]; then
        stow_flags=("-n" "-v" "${stow_flags[@]}")
    fi

    echo -e "Running: stow ${stow_flags[*]}"

    if stow "${stow_flags[@]}"; then
        echo -e "${GREEN}Symlinks created successfully.${NC}"
    else
        echo -e "${RED}Error: Stow deployment failed.${NC}" >&2
        exit 3
    fi
}


execute_undeploy() {
    check_permissions

    echo -e "${BLUE}Removing symlinks...${NC}"

    local stow_flags=("-t" "$TARGET_DIR" "-d" "$BASE_DIR" "-D" "src")

    for pattern in "${ACTIVE_IGNORE_PATTERNS[@]}"; do
        stow_flags+=("--ignore=$pattern")
    done

    if [[ "$DRY_RUN" == "true" ]]; then
        stow_flags=("-n" "-v" "${stow_flags[@]}")
    fi

    echo -e "Running: stow ${stow_flags[*]}"

    if stow "${stow_flags[@]}"; then
        echo -e "${GREEN}Symlinks removed successfully.${NC}"
    else
        echo -e "${RED}Error: Stow undeployment failed.${NC}" >&2
        exit 3
    fi
}


execute_status() {
    echo -e "${BLUE}Managed Symlinks Status in '$TARGET_DIR':${NC}"
    local total_links=0
    local dead_links=0
    local -A checked_paths=()

    while IFS= read -r -d '' file; do
        local rel_path="${file#$BASE_DIR/src/}"

        # Skip status audits for active ignore patterns
        local skip=false
        for pattern in "${ACTIVE_IGNORE_PATTERNS[@]}"; do
            if [[ "$rel_path" == "$pattern" || "$rel_path" == "$pattern"/* ]]; then
                skip=true
                break
            fi
        done
        if [[ "$skip" == "true" ]]; then
            continue
        fi

        # Fold audits to the custom folder level if inside an exclusive folded directory (matches shallowest first)
        for exclusive in "${EXCLUSIVE_FOLDED_SUBDIRECTORIES[@]}"; do
            if [[ "$rel_path" == "$exclusive" || "$rel_path" == "$exclusive"/* ]]; then
                rel_path="$exclusive"
                break
            fi
        done

        # De-duplicate audits since multiple nested files map to the same folded parent
        if [[ -n "${checked_paths[$rel_path]:-}" ]]; then
            continue
        fi
        checked_paths[$rel_path]=1

        local dest_path="$TARGET_DIR/$rel_path"

        if [[ -L "$dest_path" ]]; then
            total_links=$((total_links + 1))
            local target_resolved
            target_resolved=$(readlink -f "$dest_path" || true)

            if [[ -e "$dest_path" ]]; then
                echo -e "  ${GREEN}[Active Link]${NC} $rel_path -> $target_resolved"
            else
                echo -e "  ${RED}[Dead Link]  ${NC} $rel_path -> (missing target: $target_resolved)"
                dead_links=$((dead_links + 1))
            fi
        fi
    done < <(find "$BASE_DIR/src" -type f -print0)

    echo -e "\n${BLUE}Summary:${NC}"
    echo -e "  Total links tracked: $total_links"
    if [[ "$dead_links" -gt 0 ]]; then
        echo -e "  ${RED}Dead links found: $dead_links${NC}"
    else
        echo -e "  ${GREEN}All tracked links are healthy.${NC}"
    fi
}


# Main Orchestration Dispatch
case "$COMMAND" in
    deploy)
        execute_deploy
        ;;
    undeploy)
        execute_undeploy
        ;;
    status)
        execute_status
        ;;
esac
