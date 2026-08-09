# Terraform version manager
# https://github.com/tfutils/tfenv

() {
  local tfenv_root="${TFENV_ROOT:-$HOME/.tfenv}"

  if [[ -d "$tfenv_root" ]]; then
    export TFENV_ROOT="$tfenv_root"
    [[ -d "$TFENV_ROOT/bin" ]] && path=("$TFENV_ROOT/bin" $path)
  fi
} "$@"
