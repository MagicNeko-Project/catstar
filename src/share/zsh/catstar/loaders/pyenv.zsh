# Simple Python version management
# https://github.com/pyenv/pyenv

() {
  local pyenv_root="${PYENV_ROOT:-$HOME/.pyenv}"

  if [[ -d "$pyenv_root" ]]; then
    export PYENV_ROOT="$pyenv_root"
    [[ -d "$PYENV_ROOT/shims" ]] && path=("$PYENV_ROOT/shims" $path)
    [[ -d "$PYENV_ROOT/bin" ]] && path=("$PYENV_ROOT/bin" $path)
  fi

  if (( $+commands[pyenv] )); then
    eval "$(pyenv init - --no-rehash)"
  fi
} "$@"
