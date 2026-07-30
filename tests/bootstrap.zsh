# Environment bootstrap for test execution.

() {
  local script_dir="${${(%):-%x}:a:h}"
  local repo_root="${script_dir:h}"
  local zsh_loader="${repo_root}/src/share/zsh/catstar.zsh"

  if [[ -f "$zsh_loader" ]]; then
    source "$zsh_loader"
  fi
}
