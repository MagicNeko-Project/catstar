# Google Cloud CLI (gcloud, bq, gsutil)
# https://cloud.google.com/sdk/docs/install

() {
  local -a candidate_dirs=(
    "${GOOGLE_CLOUD_SDK_ROOT:-}"
    "/usr/share/google-cloud-sdk"
    "${HOMEBREW_PREFIX:+$HOMEBREW_PREFIX/share/google-cloud-sdk}"
    "/opt/homebrew/share/google-cloud-sdk"
    "/usr/local/share/google-cloud-sdk"
    "${HOMEBREW_PREFIX:+$HOMEBREW_PREFIX/Caskroom/google-cloud-sdk/latest/google-cloud-sdk}"
    "$HOME/.local/opt/google-cloud-sdk"
    "$HOME/google-cloud-sdk"
    "/opt/google-cloud-sdk"
  )

  local candidate
  for candidate in "${candidate_dirs[@]}"; do
    if [[ -n "$candidate" && ( -r "$candidate/path.zsh.inc" || -r "$candidate/completion.zsh.inc" ) ]]; then
      [[ -r "$candidate/path.zsh.inc" ]] && source "$candidate/path.zsh.inc"
      [[ -r "$candidate/completion.zsh.inc" ]] && source "$candidate/completion.zsh.inc"
      break
    fi
  done
} "$@"
