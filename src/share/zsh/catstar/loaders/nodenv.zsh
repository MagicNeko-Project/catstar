# Manage multiple NodeJS versions
# https://github.com/nodenv/nodenv

() {
  local nodenv_root="${NODENV_ROOT:-$HOME/.nodenv}"

  if [[ -d "$nodenv_root" ]]; then
    export NODENV_ROOT="$nodenv_root"
    [[ -d "$NODENV_ROOT/bin" ]] && path=("$NODENV_ROOT/bin" $path)
  fi

  if (( $+commands[nodenv] )); then
    eval "$(nodenv init - --no-rehash)"
  fi
} "$@"
