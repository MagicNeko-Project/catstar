# Catstar Zsh Framework Loader
# -----------------------------------------------------------------------------
# This script initializes the Catstar Zsh environment by setting up autoloaded
# functions and sourcing modular configuration files.
#
# It uses an anonymous function to prevent namespace pollution and ensures
# that all paths are resolved relative to the script location.
#
# Usage / Installation:
# Add the following line to your ~/.zshrc to load the framework:
#
#   source /path/to/catstar.zsh
#
# Options:
#   --oh-my-zsh
#     Enable loading of the Oh My Zsh framework.
#
#   --oh-my-zsh-paths <path1>:<path2>
#     Specify a custom colon-separated list of search paths for Oh My Zsh.
#     Defaults to: $ZSH, ~/.oh-my-zsh, /usr/share/oh-my-zsh, /opt/oh-my-zsh.
#
#   --clone-oh-my-zsh
#     Automatically git clone Oh My Zsh to the first search path if it is not
#     found in any of the search directories.
#
# Examples:
#   # Standard load:
#   source ~/.config/zsh/catstar.zsh
#
#   # Load with Oh My Zsh enabled:
#   source ~/.config/zsh/catstar.zsh --oh-my-zsh
#
#   # Load with Oh My Zsh, auto-cloning if missing:
#   source ~/.config/zsh/catstar.zsh --oh-my-zsh --clone-oh-my-zsh
#
#   # Load with custom Oh My Zsh path:
#   source ~/.config/zsh/catstar.zsh --oh-my-zsh --oh-my-zsh-paths "$HOME/.my-zsh"
# -----------------------------------------------------------------------------

() {
  # ---------------------------------------------------------------------------
  # 1. Initialization & Path Resolution
  # ---------------------------------------------------------------------------

  # Resolve the stowed Zsh config directory (retaining symbolic link paths)
  typeset -g CATSTAR_ZSH_ROOT="${1:a:h}"

  # Resolve the original Git repository directory (following symbolic links)
  typeset -g CATSTAR_ROOT="${1:A:h:h:h:h}"

  local catstar_directory="$CATSTAR_ZSH_ROOT/catstar"

  # Shift positional parameters so "$@" isolates only user-provided arguments
  shift

  # ---------------------------------------------------------------------------
  # 2. Default Configurations & Local State Setup
  # ---------------------------------------------------------------------------

  local -a default_oh_my_zsh_search_paths
  if [[ -n "$ZSH" ]]; then
    default_oh_my_zsh_search_paths+=("$ZSH")
  fi
  default_oh_my_zsh_search_paths+=(
    "$HOME/.oh-my-zsh"
    "/usr/share/oh-my-zsh"
    "/opt/oh-my-zsh"
  )

  local should_load_oh_my_zsh=false
  local should_clone_oh_my_zsh_if_missing=false
  local -a oh_my_zsh_search_paths
  oh_my_zsh_search_paths=("${default_oh_my_zsh_search_paths[@]}")

  # ---------------------------------------------------------------------------
  # 3. Inner Helper Functions (Decoupled Operations)
  # ---------------------------------------------------------------------------

  # Parses all input flags and sets local configuration states
  function parse_loader_command_line_arguments() {
    while (( $# > 0 )); do
      case "$1" in
        --oh-my-zsh)
          should_load_oh_my_zsh=true
          shift
          ;;
        --oh-my-zsh-paths)
          if [[ -n "$2" && "$2" != -* ]]; then
            # Split the colon-separated paths string into a native Zsh array
            oh_my_zsh_search_paths=(${(s/:/)2})
            shift 2
          else
            shift
          fi
          ;;
        --clone-oh-my-zsh)
          should_clone_oh_my_zsh_if_missing=true
          shift
          ;;
        *)
          # Skip unrecognized options
          shift
          ;;
      esac
    done
  }

  # Clones the upstream Oh My Zsh repository to the specified path
  function clone_oh_my_zsh_repository() {
    local target_directory="$1"
    if [[ -z "$target_directory" ]]; then
      echo "Catstar Loader Error: Target directory for cloning is empty." >&2
      return 1
    fi

    # Resolve absolute directory path, expanding any tildes
    target_directory="${target_directory/#\~/$HOME}"
    target_directory="${target_directory:A}"

    echo "Catstar Loader: Oh My Zsh not found in search paths. Cloning to: $target_directory"

    if ! command -v git >/dev/null 2>&1; then
      echo "Catstar Loader Error: 'git' command is not installed. Cannot clone Oh My Zsh." >&2
      return 1
    fi

    local parent_directory="${target_directory:h}"
    mkdir -p "$parent_directory"

    local git_repository_url="https://github.com/ohmyzsh/ohmyzsh.git"
    if git clone "$git_repository_url" "$target_directory"; then
      return 0
    else
      echo "Catstar Loader Error: Failed to clone Oh My Zsh repository from $git_repository_url" >&2
      return 1
    fi
  }

  # Traverses candidate paths, loads the framework on first match, or clones if missing
  function search_and_load_oh_my_zsh() {
    local is_oh_my_zsh_framework_found=false
    local candidate_path

    for candidate_path in "${oh_my_zsh_search_paths[@]}"; do
      # Resolve tildes to actual user home directories
      candidate_path="${candidate_path/#\~/$HOME}"
      local bootstrap_script="$candidate_path/oh-my-zsh.sh"

      if [[ -f "$bootstrap_script" ]]; then
        export ZSH="$candidate_path"
        source "$bootstrap_script"
        is_oh_my_zsh_framework_found=true
        break
      fi
    done

    # If missing and cloning is allowed, install the framework automatically
    if [[ "$is_oh_my_zsh_framework_found" == false && "$should_clone_oh_my_zsh_if_missing" == true ]]; then
      local primary_target_path="${oh_my_zsh_search_paths[1]}"
      
      if clone_oh_my_zsh_repository "$primary_target_path"; then
        # Resolve resolved absolute path after cloning
        primary_target_path="${primary_target_path/#\~/$HOME}"
        primary_target_path="${primary_target_path:A}"

        export ZSH="$primary_target_path"
        source "$primary_target_path/oh-my-zsh.sh"
        is_oh_my_zsh_framework_found=true
      fi
    fi
  }

  # ---------------------------------------------------------------------------
  # 4. Framework Execution Sequence
  # ---------------------------------------------------------------------------

  # Step A: Parse user arguments
  parse_loader_command_line_arguments "$@"

  # Step B: Load or bootstrap Oh My Zsh if requested
  if [[ "$should_load_oh_my_zsh" == true ]]; then
    search_and_load_oh_my_zsh
  fi

  # Step C: Modular function autoloading (Catstar modules)
  local functions_directory="$catstar_directory/functions"
  if [[ -d "$functions_directory" ]]; then
    # Ensure fpath doesn't already have the directory registered to avoid duplication
    if [[ "${fpath[(r)$functions_directory]}" != "$functions_directory" ]]; then
      fpath=("$functions_directory" $fpath)
    fi

    # Autoload all non-hidden modules, excluding completion files starting with an underscore (_)
    setopt localoptions extendedglob
    autoload -Uz "$functions_directory"/(^_*)(N:t)
  fi

  # Step D: Sourcing auxiliary modular configuration scripts (.zsh)
  local configuration_script
  for configuration_script in "$catstar_directory"/*.zsh(N); do
    source "$configuration_script"
  done

  # ---------------------------------------------------------------------------
  # 5. Namespace Cleanup
  # ---------------------------------------------------------------------------
  unfunction parse_loader_command_line_arguments
  unfunction clone_oh_my_zsh_repository
  unfunction search_and_load_oh_my_zsh
} "${(%):-%x}" "$@"
