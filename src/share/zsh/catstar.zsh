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
  # 1. Path Resolution
  # Resolve the stowed Zsh config directory (retaining symbolic link paths)
  typeset -g CATSTAR_ZSH_ROOT="${1:a:h}"

  # Resolve the original Git repository directory (following symbolic links)
  typeset -g CATSTAR_ROOT="${1:A:h:h:h:h}"

  local catstar_dir="$CATSTAR_ZSH_ROOT/catstar"

  # Shift the script path to isolate user arguments
  shift

  # 2. Argument Parsing & Option Setup
  local load_omz=false
  local clone_omz=false
  typeset -a omz_search_paths

  # Populate default search paths
  if [[ -n "$ZSH" ]]; then
    omz_search_paths+=("$ZSH")
  fi
  omz_search_paths+=("$HOME/.oh-my-zsh" "/usr/share/oh-my-zsh" "/opt/oh-my-zsh")

  while (( $# > 0 )); do
    case "$1" in
      --oh-my-zsh)
        load_omz=true
        shift
        ;;
      --oh-my-zsh-paths)
        if [[ -n "$2" && "$2" != -* ]]; then
          omz_search_paths=(${(s/:/)2})
          shift 2
        else
          shift
        fi
        ;;
      --clone-oh-my-zsh)
        clone_omz=true
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  # 3. Oh My Zsh Integration
  if [[ "$load_omz" == true ]]; then
    local omz_found=false
    local search_path
    for search_path in "${omz_search_paths[@]}"; do
      # Expand tilde if present
      search_path="${search_path/#\~/$HOME}"
      if [[ -f "$search_path/oh-my-zsh.sh" ]]; then
        export ZSH="$search_path"
        source "$search_path/oh-my-zsh.sh"
        omz_found=true
        break
      fi
    done

    if [[ "$omz_found" == false && "$clone_omz" == true ]]; then
      local target_dir="${omz_search_paths[1]}"
      if [[ -n "$target_dir" ]]; then
        target_dir="${target_dir/#\~/$HOME}"
        target_dir="${target_dir:A}"

        echo "Catstar Loader: Oh My Zsh not found. Cloning to $target_dir..."
        if command -v git >/dev/null 2>&1; then
          mkdir -p "$(dirname "$target_dir")"
          if git clone https://github.com/ohmyzsh/ohmyzsh.git "$target_dir"; then
            export ZSH="$target_dir"
            source "$target_dir/oh-my-zsh.sh"
          else
            echo "Catstar Loader Error: Failed to clone Oh My Zsh." >&2
          fi
        else
          echo "Catstar Loader Error: git command not found. Cannot clone Oh My Zsh." >&2
        fi
      fi
    fi
  fi

  # 4. Function Autoloading
  # We add the functions directory to fpath and mark all files for autoloading.
  # This improves startup time as functions are only loaded when first used.
  local functions_dir="$catstar_dir/functions"
  if [[ -d "$functions_dir" ]]; then
    # Ensure it's not already in fpath to avoid duplicates
    if [[ "${fpath[(r)$functions_dir]}" != "$functions_dir" ]]; then
      fpath=("$functions_dir" $fpath)
    fi

    # Autoload all non-hidden files in the functions directory, EXCLUDING completion files (_*)
    # -U: suppress alias expansion, -z: use zsh style
    # (^_*): excludes files starting with underscore
    # (N:t): N for nullglob (don't error if empty), t for tail (basename only)
    setopt localoptions extendedglob
    autoload -Uz "$functions_dir"/(^_*)(N:t)
  fi

  # 5. Modular Configuration Loading
  # Load all .zsh files from the catstar directory in alphabetical order.
  local script
  for script in "$catstar_dir"/*.zsh(N); do
    source "$script"
  done
} "${(%):-%x}" "$@"
