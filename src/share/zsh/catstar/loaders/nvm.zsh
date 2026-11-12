# Node Version Manager - POSIX-compliant bash script to manage multiple active node.js versions
# https://github.com/nvm-sh/nvm

_catstar_source_nvm() {
  source "$NVM_DIR/nvm.sh" "$@"

  if [[ ! -s "$NVM_DIR/bash_completion" ]]; then
    return 0
  fi

  # nvm's bash_completion runs its own compinit under zsh, which re-scans fpath
  # and adds over a second to startup. When compinit has already run, blank
  # ZSH_VERSION to skip that block and register through bashcompinit directly.
  if (( $+functions[compdef] )); then
    autoload -U +X bashcompinit && bashcompinit
    ZSH_VERSION= source "$NVM_DIR/bash_completion"
  else
    source "$NVM_DIR/bash_completion"
  fi
}

() {
  local -a candidate_directories=(
    "$NVM_DIR"
    "$HOME/.nvm"
    "${HOMEBREW_PREFIX:+$HOMEBREW_PREFIX/opt/nvm}"
    "/opt/homebrew/opt/nvm"
    "/usr/local/opt/nvm"
    "/usr/local/nvm"
  )

  local candidate nvm_directory=""
  for candidate in "${candidate_directories[@]}"; do
    if [[ -n "$candidate" && -s "$candidate/nvm.sh" ]]; then
      nvm_directory="$candidate"
      break
    fi
  done

  if [[ -z "$nvm_directory" ]]; then
    return 0
  fi

  export NVM_DIR="$nvm_directory"

  # Sourcing nvm.sh costs over a second, mostly spent activating the default
  # Node. When an nvm-managed node is already first on PATH (inherited from a
  # parent shell), defer loading to the first nvm call and skip re-activation.
  if [[ "${commands[node]}" == "$NVM_DIR"/versions/node/* ]]; then
    nvm() {
      unfunction nvm
      _catstar_source_nvm --no-use
      nvm "$@"
    }
    return 0
  fi

  _catstar_source_nvm
} "$@"
