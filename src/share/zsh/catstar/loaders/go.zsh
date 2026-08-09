# Build fast, reliable, and efficient software at scale
# https://go.dev

() {
  local gopath="${GOPATH:-$HOME/go}"
  local go_found=false

  if (( $+commands[go] )) || [[ -d "/usr/local/go/bin" ]] || [[ -d "$gopath/bin" ]]; then
    go_found=true
  fi

  if [[ "$go_found" == false ]]; then
    return 0
  fi

  export GOPATH="$gopath"

  [[ -d "/usr/local/go/bin" ]] && path=("/usr/local/go/bin" $path)
  [[ -d "$GOPATH/bin" ]] && path=("$GOPATH/bin" $path)
} "$@"
