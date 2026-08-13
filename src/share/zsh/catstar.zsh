# Catstar Zsh Framework Loader
# -----------------------------------------------------------------------------
# This script initializes the Catstar Zsh environment by setting up autoloaded
# functions, interactive plugin loaders, and sourcing modular configuration files.
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
#   --loader <name>
#     Specify an interactive environment loader plugin to run (e.g. brew, pyenv, nvm).
#     Fails fast if the specified loader plugin is missing.
#
#   --loaders <list>
#     Specify a comma- or colon-separated list of loaders to run (e.g. brew,pyenv,nvm).
#
#   --list-loaders
#     List all available plugin loaders in the repository.
#
# Examples:
#   # Standard load:
#   source ~/.config/zsh/catstar.zsh
#
#   # Load with Oh My Zsh enabled:
#   source ~/.config/zsh/catstar.zsh --oh-my-zsh
#
#   # Load with specific plugin loaders:
#   source ~/.config/zsh/catstar.zsh --loader brew --loader pyenv
#   source ~/.config/zsh/catstar.zsh --loaders brew,pyenv,nvm
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

  # Enforce built-in array deduplication globally for standard environment paths
  typeset -g -U path fpath manpath

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
  local should_list_loaders=false
  local -a oh_my_zsh_search_paths
  oh_my_zsh_search_paths=("${default_oh_my_zsh_search_paths[@]}")

  local -a requested_loaders
  if [[ "${(t)CATSTAR_LOADERS}" == *array* ]]; then
    requested_loaders=("${CATSTAR_LOADERS[@]}")
  elif [[ -n "$CATSTAR_LOADERS" ]]; then
    local env_loaders="${CATSTAR_LOADERS//[: ]/,}"
    requested_loaders=("${(@s/,/)env_loaders}")
  fi

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
      --loader)
        if [[ -n "$2" && "$2" != -* ]]; then
          requested_loaders+=("$2")
          shift 2
        else
          shift
        fi
        ;;
      --loaders)
        if [[ -n "$2" && "$2" != -* ]]; then
          local raw_loaders="$2"
          raw_loaders="${raw_loaders//[: ]/,}"
          local -a parsed_loaders
          parsed_loaders=("${(@s/,/)raw_loaders}")
          requested_loaders+=("${parsed_loaders[@]}")
          shift 2
        else
          shift
        fi
        ;;
      --list-loaders)
        should_list_loaders=true
        shift
        ;;
      *)
        # Skip unrecognized options
        shift
        ;;
    esac
  done

  # Register core framework functions in $fpath
  local core_functions_directory="$catstar_directory/core/functions"
  if [[ -d "$core_functions_directory" ]]; then
    typeset -g -U fpath
    fpath=("$core_functions_directory" $fpath)
    autoload -Uz "$core_functions_directory"/*(N:t)
  fi

  # ---------------------------------------------------------------------------
  # 4. List Loaders Mode
  # ---------------------------------------------------------------------------
  local loaders_directory="$catstar_directory/loaders"
  if [[ "$should_list_loaders" == true ]]; then
    catstar_load_plugins --dir "$loaders_directory" --list
    return 0
  fi

  # ---------------------------------------------------------------------------
  # 5. Oh My Zsh Integration
  # ---------------------------------------------------------------------------

  local -a omz_flags=()
  [[ "$should_load_oh_my_zsh" == true ]] && omz_flags+=(--load)
  [[ "$should_clone_oh_my_zsh_if_missing" == true ]] && omz_flags+=(--clone)
  local path_entry
  for path_entry in "${oh_my_zsh_search_paths[@]}"; do
    omz_flags+=(--path "$path_entry")
  done

  catstar_init_omz "${omz_flags[@]}"

  # ---------------------------------------------------------------------------
  # 6. Custom Catstar Function Autoloading
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
  # 7. Plugin Loaders Execution
  # ---------------------------------------------------------------------------
  local -a loader_flags=(--dir "$loaders_directory")
  local req
  for req in "${requested_loaders[@]}"; do
    loader_flags+=(--loader "$req")
  done

  catstar_load_plugins "${loader_flags[@]}" || return 1

  # ---------------------------------------------------------------------------
  # 8. Modular Configuration Loading
  # ---------------------------------------------------------------------------
  local configuration_script
  for configuration_script in "$catstar_directory"/*.zsh(N); do
    source "$configuration_script"
  done
} "${(%):-%x}" "$@"
