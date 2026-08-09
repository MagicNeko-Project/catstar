# Fast and simple Node.js version manager, built in Rust
# https://fnm.vercel.app

() {
  local fnm_bin

  if (( $+commands[fnm] )); then
    fnm_bin="fnm"
  elif [[ -x "$HOME/.fnm/fnm" ]]; then
    fnm_bin="$HOME/.fnm/fnm"
  elif [[ -x "$HOME/.local/share/fnm/fnm" ]]; then
    fnm_bin="$HOME/.local/share/fnm/fnm"
  else
    return 0
  fi

  if [[ "$fnm_bin" != "fnm" ]]; then
    path=("${fnm_bin:h}" $path)
  fi

  eval "$("$fnm_bin" env)"
} "$@"
