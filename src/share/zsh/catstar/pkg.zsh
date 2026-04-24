# Catstar Package Manager Aliases - 2026 Edition
# Wrap implementation in an anonymous function to avoid variable leakage.

() {
  local PACMAN_PRIVILEGED_OPERATIONS=(
      Sc Scc Sccc Su Sw S Sy Syu
      R Rn Rns Rs
  )

  local PACMAN_OPERATIONS=(
      Sg Si Sii Sl Ss
      Q Qc Qe Qi Qk Ql Qm Qo Qp Qs Qu
  )

  local pacman_cmd privileged_cmd
  local p_candidate

  # Use Zsh native command lookup
  for p_candidate in pacman pacapt; do
    if (( $+commands[$p_candidate] )); then
      pacman_cmd=$p_candidate

      # Use native file ownership check
      if [[ ! -O =$pacman_cmd ]]; then
        privileged_cmd="sudo $pacman_cmd"
      else
        privileged_cmd="$pacman_cmd"
      fi
      break
    fi
  done

  if [[ -n $pacman_cmd ]]; then
    local op
    for op in $PACMAN_PRIVILEGED_OPERATIONS; do
      alias "$op"="$privileged_cmd -$op"
    done
    for op in $PACMAN_OPERATIONS; do
      alias "$op"="$pacman_cmd -$op"
    done
  fi
}
