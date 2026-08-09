# The Software Development Kit Manager
# https://sdkman.io

() {
  local sdkman_dir="${SDKMAN_DIR:-$HOME/.sdkman}"

  if [[ -s "$sdkman_dir/bin/sdkman-init.sh" ]]; then
    export SDKMAN_DIR="$sdkman_dir"
    source "$sdkman_dir/bin/sdkman-init.sh"
  fi
} "$@"
