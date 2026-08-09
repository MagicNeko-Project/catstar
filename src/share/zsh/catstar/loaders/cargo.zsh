# Rust’s package manager and build system
# https://doc.rust-lang.org/cargo/

() {
  local cargo_home="${CARGO_HOME:-$HOME/.cargo}"

  if [[ -s "$cargo_home/env" ]]; then
    source "$cargo_home/env"
  elif [[ -d "$cargo_home/bin" ]]; then
    path=("$cargo_home/bin" $path)
  fi
} "$@"
