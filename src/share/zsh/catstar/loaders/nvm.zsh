# Node Version Manager - POSIX-compliant bash script to manage multiple active node.js versions
# https://github.com/nvm-sh/nvm

() {
  local nvm_dir="${NVM_DIR:-$HOME/.nvm}"

  if [[ ! -s "$nvm_dir/nvm.sh" ]]; then
    if [[ -n "$HOMEBREW_PREFIX" && -s "$HOMEBREW_PREFIX/opt/nvm/nvm.sh" ]]; then
      nvm_dir="$HOMEBREW_PREFIX/opt/nvm"
    elif [[ -s "/opt/homebrew/opt/nvm/nvm.sh" ]]; then
      nvm_dir="/opt/homebrew/opt/nvm"
    elif [[ -s "/usr/local/opt/nvm/nvm.sh" ]]; then
      nvm_dir="/usr/local/opt/nvm"
    else
      return 0
    fi
  fi

  export NVM_DIR="$nvm_dir"

  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    source "$NVM_DIR/nvm.sh"
  fi

  if [[ -s "$NVM_DIR/bash_completion" ]]; then
    source "$NVM_DIR/bash_completion"
  fi
} "$@"
