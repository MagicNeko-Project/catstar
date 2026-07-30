# Environment bootstrap for test execution.

() {
  local script_dir="${${(%):-%x}:a:h}"
  local repo_root="${script_dir:h}"
  local zsh_loader="${repo_root}/src/share/zsh/catstar.zsh"
  local functions_dir="${repo_root}/src/share/zsh/catstar/functions"

  if [[ -f "$zsh_loader" ]]; then
    source "$zsh_loader"
  fi

  if [[ -d "$functions_dir" ]]; then
    fpath=( "$functions_dir" $fpath )
    autoload -Uz "$functions_dir"/*(N:t)
  fi
}
