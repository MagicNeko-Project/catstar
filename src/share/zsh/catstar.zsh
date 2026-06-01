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
  # 1. Path Resolution
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
  # 3. Command-Line Argument Parsing (Procedural Logic)
  # ---------------------------------------------------------------------------
  while (( $# > 0 )); do
    case "$1" in
      --oh-my-zsh)
        should_load_oh_my_zsh=true
        shift
        ;;
      --oh-my-zsh-paths)
        if [[ -n "$2" && "$2" != -* ]]; then
          # Split the colon-separated paths string into a native Zsh array using the (@) flag
          oh_my_zsh_search_paths=("${(@s/:/)2}")
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

  # ---------------------------------------------------------------------------
  # 4. Oh My Zsh Integration (Procedural Logic)
  # ---------------------------------------------------------------------------
  if [[ "$should_load_oh_my_zsh" == true ]]; then
    local is_oh_my_zsh_framework_found=false
    local candidate_path

    for candidate_path in "${oh_my_zsh_search_paths[@]}"; do
      # Expand tilde safely via string replacement and compute lowercase absolute path
      candidate_path="${candidate_path/#\~/$HOME}"
      candidate_path="${candidate_path:a}"
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

      if [[ -n "$primary_target_path" ]]; then
        # Expand tilde safely via string replacement and resolve lowercase absolute path
        primary_target_path="${primary_target_path/#\~/$HOME}"
        primary_target_path="${primary_target_path:a}"

        print "Catstar Loader: Oh My Zsh not found in search paths. Cloning to: $primary_target_path"

        if ! command -v git >/dev/null 2>&1; then
          print -u2 "Catstar Loader Error: 'git' command is not installed. Cannot clone Oh My Zsh."
        else
          local parent_directory="${primary_target_path:h}"
          mkdir -p "$parent_directory"

          local git_repository_url="https://github.com/ohmyzsh/ohmyzsh.git"
          if git clone "$git_repository_url" "$primary_target_path"; then
            export ZSH="$primary_target_path"
            source "$primary_target_path/oh-my-zsh.sh"
            is_oh_my_zsh_framework_found=true
          else
            print -u2 "Catstar Loader Error: Failed to clone Oh My Zsh repository from $git_repository_url"
          fi
        fi
      fi
    fi
  fi

  # ---------------------------------------------------------------------------
  # 5. Custom Catstar Function Autoloading
  # ---------------------------------------------------------------------------
  local functions_directory="$catstar_directory/functions"
  if [[ -d "$functions_directory" ]]; then
    # Enforce built-in array deduplication via unique global declaration
    typeset -g -U fpath
    fpath=("$functions_directory" $fpath)

    # Autoload all non-hidden modules, excluding completion files starting with an underscore (_)
    # We isolate the setopt localoptions inside a nested anonymous function so it does
    # not affect options configured by Oh My Zsh (like promptsubst) in the outer scope.
    () {
      setopt localoptions extendedglob
      autoload -Uz "$functions_directory"/(^_*)(N:t)
    }
  fi

  # ---------------------------------------------------------------------------
  # 6. Modular Configuration Loading
  # ---------------------------------------------------------------------------
  local configuration_script
  for configuration_script in "$catstar_directory"/*.zsh(N); do
    source "$configuration_script"
  done
} "${(%):-%x}" "$@"
