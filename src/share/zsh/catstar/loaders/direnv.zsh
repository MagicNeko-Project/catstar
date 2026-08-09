# Unclutter your .profile - environment switcher for the shell
# https://direnv.net

() {
  if (( ! $+commands[direnv] )); then
    return 0
  fi

  eval "$(direnv hook zsh)"
} "$@"
