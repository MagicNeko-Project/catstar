# Thin wrapper around PHP binaries to manage multiple PHP versions
# https://github.com/phpenv/phpenv

() {
  local phpenv_root="${PHPENV_ROOT:-$HOME/.phpenv}"

  if [[ -d "$phpenv_root" ]]; then
    export PHPENV_ROOT="$phpenv_root"
    [[ -d "$PHPENV_ROOT/bin" ]] && path=("$PHPENV_ROOT/bin" $path)
  fi

  if (( $+commands[phpenv] )); then
    eval "$(phpenv init -)"
  fi
} "$@"
