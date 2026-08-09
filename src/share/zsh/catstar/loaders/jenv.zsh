# Java version management tool
# https://www.jenv.be

() {
  local jenv_root="${JENV_ROOT:-$HOME/.jenv}"

  if [[ -d "$jenv_root" ]]; then
    export JENV_ROOT="$jenv_root"
    [[ -d "$JENV_ROOT/bin" ]] && path=("$JENV_ROOT/bin" $path)
  fi

  if (( $+commands[jenv] )); then
    eval "$(jenv init - --no-rehash)"
  fi
} "$@"
