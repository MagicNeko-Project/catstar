# Go version management
# https://github.com/goenv/goenv

() {
  local goenv_root="${GOENV_ROOT:-$HOME/.goenv}"

  if [[ -d "$goenv_root" ]]; then
    export GOENV_ROOT="$goenv_root"
    [[ -d "$GOENV_ROOT/bin" ]] && path=("$GOENV_ROOT/bin" $path)
  fi

  if (( $+commands[goenv] )); then
    eval "$(goenv init -)"
  fi
} "$@"
