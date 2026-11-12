# Behavioral tests for the nvm loader
# -----------------------------------------------------------------------------

describe "NvmLoaderTest"

typeset -g TEST_WORKSPACE_DIR=""
typeset -g NVM_LOADER_PATH=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/nvm_loader_test_XXXXXX")"
  NVM_LOADER_PATH="$CATSTAR_ROOT/src/share/zsh/catstar/loaders/nvm.zsh"

  # Stub nvm.sh records how it was sourced and defines a recognizable nvm.
  export NVM_DIR="$TEST_WORKSPACE_DIR/nvm"
  mkdir -p "$NVM_DIR"
  cat > "$NVM_DIR/nvm.sh" <<'EOF'
NVM_STUB_SOURCE_COUNT=$(( ${NVM_STUB_SOURCE_COUNT:-0} + 1 ))
NVM_STUB_SOURCE_ARGUMENTS="$*"
nvm() { print -r -- "stub nvm $*"; }
EOF
  unset NVM_STUB_SOURCE_COUNT NVM_STUB_SOURCE_ARGUMENTS
}

TearDown() {
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

test_nvm_loader_sources_eagerly_when_managed_node_is_inactive() {
  local loader_output_file="$TEST_WORKSPACE_DIR/loader_output"

  PATH="/usr/bin:/bin"
  source "$NVM_LOADER_PATH" >"$loader_output_file" 2>&1

  assert_eq "$NVM_STUB_SOURCE_COUNT" "1" "nvm.sh must be sourced during loading"
  expect_eq "$NVM_STUB_SOURCE_ARGUMENTS" "" "Eager loading must let nvm activate the default node"
  expect_eq "$NVM_DIR" "$TEST_WORKSPACE_DIR/nvm" "NVM_DIR must point at the discovered installation"
  expect_eq "$(<"$loader_output_file")" "" "Loading must not print anything"
}

test_nvm_loader_defers_when_managed_node_is_on_path() {
  local node_bin_directory="$NVM_DIR/versions/node/v0.0.0-test/bin"
  mkdir -p "$node_bin_directory"
  print '#!/bin/sh' > "$node_bin_directory/node"
  chmod +x "$node_bin_directory/node"

  PATH="$node_bin_directory:/usr/bin:/bin"
  rehash
  source "$NVM_LOADER_PATH"

  expect_eq "${NVM_STUB_SOURCE_COUNT:-0}" "0" "nvm.sh must not be sourced during loading"
  assert_eq "${functions[nvm]:+defined}" "defined" "A deferred nvm function must be defined"

  local first_call_output
  first_call_output=$(nvm current; print -r -- "count=$NVM_STUB_SOURCE_COUNT args=$NVM_STUB_SOURCE_ARGUMENTS")

  expect_contains "$first_call_output" "stub nvm current" "First call must dispatch to the real nvm"
  expect_contains "$first_call_output" "count=1 args=--no-use" "First call must source nvm.sh once without re-activating node"
}
