# Catstar Loader - 2026 Edition
# Strictly follow modern Zsh best practices.

# Avoid polluting the global namespace during initialization.
() {
  CATSTAR_ZSH_ROOT="${1:A:h}"
  CATSTAR_ROOT="${CATSTAR_ZSH_ROOT:h:h:h}"

  local catstar_dir="$CATSTAR_ZSH_ROOT/catstar"

  # 1. Performance: Setup autoloading for complex functions
  local functions_dir="$catstar_dir/functions"
  if [[ -d $functions_dir ]]; then
    fpath=($functions_dir $fpath)
    autoload -Uz $functions_dir/*(N:t)
  fi

  # 2. Modern Loader: Use Zsh native nullglob iteration
  # Load configuration and aliases
  local script
  for script in $catstar_dir/*.zsh(N); do
    source "$script"
  done
} "$0"
