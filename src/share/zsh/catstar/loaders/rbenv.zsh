# Groom your app’s Ruby environment
# https://github.com/rbenv/rbenv

() {
  local rbenv_root="${RBENV_ROOT:-$HOME/.rbenv}"

  if [[ -d "$rbenv_root" ]]; then
    export RBENV_ROOT="$rbenv_root"
    [[ -d "$RBENV_ROOT/bin" ]] && path=("$RBENV_ROOT/bin" $path)
  fi

  if (( $+commands[rbenv] )); then
    eval "$(rbenv init - --no-rehash)"
  fi
} "$@"
