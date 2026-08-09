# The Missing Package Manager for macOS (and Linux)
# https://brew.sh

() {
  local brew_exe candidate

  if (( $+commands[brew] )); then
    brew_exe="brew"
  else
    local -a candidate_paths
    candidate_paths=(
      "/opt/homebrew/bin/brew"
      "/home/linuxbrew/.linuxbrew/bin/brew"
      "$HOME/.linuxbrew/bin/brew"
      "/Users/brew/.brew/bin/brew"
      "$HOME/.brew/bin/brew"
      "/usr/local/bin/brew"
    )
    for candidate in "${candidate_paths[@]}"; do
      if [[ -x "$candidate" ]]; then
        brew_exe="$candidate"
        break
      fi
    done
  fi

  if [[ -n "$brew_exe" ]]; then
    eval "$("$brew_exe" shellenv)"
  fi
} "$@"
