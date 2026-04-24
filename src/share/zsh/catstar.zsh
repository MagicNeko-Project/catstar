# Catstar Zsh Framework Loader
# -----------------------------------------------------------------------------
# This script initializes the Catstar Zsh environment by setting up autoloaded
# functions and sourcing modular configuration files.
#
# It uses an anonymous function to prevent namespace pollution and ensures
# that all paths are resolved relative to the script location.
# -----------------------------------------------------------------------------

() {
  # 1. Path Resolution
  # A: absolute path, h: head (dirname)
  # Define root variables globally so they persist in the shell session,
  # but without 'export' to avoid polluting subprocess environments.
  typeset -g CATSTAR_ZSH_ROOT="${1:A:h}"
  typeset -g CATSTAR_ROOT="${CATSTAR_ZSH_ROOT:h:h:h}"

  local catstar_dir="$CATSTAR_ZSH_ROOT/catstar"

  # 2. Function Autoloading
  # We add the functions directory to fpath and mark all files for autoloading.
  # This improves startup time as functions are only loaded when first used.
  local functions_dir="$catstar_dir/functions"
  if [[ -d "$functions_dir" ]]; then
    # Ensure it's not already in fpath to avoid duplicates
    if [[ "${fpath[(r)$functions_dir]}" != "$functions_dir" ]]; then
      fpath=("$functions_dir" $fpath)
    fi
    
    # Autoload all non-hidden files in the functions directory
    # -U: suppress alias expansion, -z: use zsh style
    # (N:t): N for nullglob (don't error if empty), t for tail (basename only)
    autoload -Uz "$functions_dir"/*(N:t)
  fi

  # 3. Modular Configuration Loading
  # Load all .zsh files from the catstar directory in alphabetical order.
  local script
  for script in "$catstar_dir"/*.zsh(N); do
    source "$script"
  done
} "${(%):-%x}"
