# Behavioral tests for the gcloud loader
# -----------------------------------------------------------------------------

describe "GcloudLoaderTest"

typeset -g TEST_WORKSPACE_DIR=""
typeset -g GCLOUD_LOADER_PATH=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gcloud_loader_test_XXXXXX")"
  GCLOUD_LOADER_PATH="$CATSTAR_ROOT/src/share/zsh/catstar/loaders/gcloud.zsh"
  unset GOOGLE_CLOUD_SDK_ROOT GCLOUD_STUB_EVENTS
}

TearDown() {
  unset GOOGLE_CLOUD_SDK_ROOT GCLOUD_STUB_EVENTS
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

test_gcloud_loader_sources_path_and_completion_from_root_override() {
  local sdk_dir="$TEST_WORKSPACE_DIR/sdk"
  local loader_output_file="$TEST_WORKSPACE_DIR/loader_output"
  mkdir -p "$sdk_dir"

  print -r -- 'GCLOUD_STUB_EVENTS="${GCLOUD_STUB_EVENTS}path;"' > "$sdk_dir/path.zsh.inc"
  print -r -- 'GCLOUD_STUB_EVENTS="${GCLOUD_STUB_EVENTS}completion;"' > "$sdk_dir/completion.zsh.inc"

  GOOGLE_CLOUD_SDK_ROOT="$sdk_dir"
  source "$GCLOUD_LOADER_PATH" >"$loader_output_file" 2>&1
  local status_code=$?

  assert_eq "$status_code" "0" "gcloud loader must exit 0 when sourcing both inc files"
  expect_eq "$GCLOUD_STUB_EVENTS" "path;completion;" "gcloud loader must source path.zsh.inc then completion.zsh.inc"
  expect_eq "$(<"$loader_output_file")" "" "gcloud loader must not print anything"
}

test_gcloud_loader_sources_when_only_path_inc_exists() {
  local sdk_dir="$TEST_WORKSPACE_DIR/sdk-path-only"
  mkdir -p "$sdk_dir"

  print -r -- 'GCLOUD_STUB_EVENTS="${GCLOUD_STUB_EVENTS}path;"' > "$sdk_dir/path.zsh.inc"

  GOOGLE_CLOUD_SDK_ROOT="$sdk_dir"
  source "$GCLOUD_LOADER_PATH"
  local status_code=$?

  assert_eq "$status_code" "0" "gcloud loader must exit 0 when only path.zsh.inc exists"
  expect_eq "$GCLOUD_STUB_EVENTS" "path;" "gcloud loader must source path.zsh.inc"
}

test_gcloud_loader_sources_when_only_completion_inc_exists() {
  local sdk_dir="$TEST_WORKSPACE_DIR/sdk-completion-only"
  mkdir -p "$sdk_dir"

  print -r -- 'GCLOUD_STUB_EVENTS="${GCLOUD_STUB_EVENTS}completion;"' > "$sdk_dir/completion.zsh.inc"

  GOOGLE_CLOUD_SDK_ROOT="$sdk_dir"
  source "$GCLOUD_LOADER_PATH"
  local status_code=$?

  assert_eq "$status_code" "0" "gcloud loader must exit 0 when only completion.zsh.inc exists"
  expect_eq "$GCLOUD_STUB_EVENTS" "completion;" "gcloud loader must source completion.zsh.inc"
}

test_gcloud_loader_stops_at_first_matching_candidate() {
  local primary_dir="$TEST_WORKSPACE_DIR/primary"
  local secondary_prefix="$TEST_WORKSPACE_DIR/homebrew"
  mkdir -p "$primary_dir" "$secondary_prefix/share/google-cloud-sdk"

  print -r -- 'GCLOUD_STUB_EVENTS="${GCLOUD_STUB_EVENTS}primary;"' > "$primary_dir/path.zsh.inc"
  print -r -- 'GCLOUD_STUB_EVENTS="${GCLOUD_STUB_EVENTS}secondary;"' > "$secondary_prefix/share/google-cloud-sdk/path.zsh.inc"

  GOOGLE_CLOUD_SDK_ROOT="$primary_dir"
  local HOMEBREW_PREFIX="$secondary_prefix"
  source "$GCLOUD_LOADER_PATH"

  expect_eq "$GCLOUD_STUB_EVENTS" "primary;" "gcloud loader must stop after the first matching candidate directory"
}
