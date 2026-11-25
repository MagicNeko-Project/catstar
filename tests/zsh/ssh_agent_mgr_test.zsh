# Unit Tests for SSH Agent Manager (ssh-agent-mgr)
# -----------------------------------------------------------------------------

describe "SshAgentMgrTest"

typeset -g _SSH_AGENT_MGR_PATH="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar/functions/ssh-agent-mgr"

ssh-agent-mgr() {
  source "$_SSH_AGENT_MGR_PATH" "$@"
}

TearDown() {
  unset _CATSTAR_KNOWN_SSH_SOCKETS
}

test_ssh_agent_mgr_help_flag() {
  local output status_code
  output=$(ssh-agent-mgr --help)
  status_code=$?

  assert_eq "$status_code" "0" "ssh-agent-mgr --help should exit with status 0"
  expect_contains "$output" "=== SSH Agent Manager (ssh-agent-mgr) ==="
  expect_contains "$output" "Usage:"

  output=$(ssh-agent-mgr -h)
  status_code=$?
  assert_eq "$status_code" "0" "ssh-agent-mgr -h should exit with status 0"
}

test_ssh_agent_mgr_no_sockets_found() {
  local output status_code
  output=$(
    export SSH_AUTH_SOCK=""
    export XDG_RUNTIME_DIR="/tmp/nonexistent_xdg_dir_12345"
    typeset -g -A _CATSTAR_KNOWN_SSH_SOCKETS=()
    ssh-agent-mgr 2>&1
  )
  status_code=$?

  if [[ "$output" == *"No SSH agent sockets found"* || "$output" == *"Found candidate sockets, but none are active SSH agents"* ]]; then
    assert_eq "$status_code" "1" "Should return 1 when no active agent sockets are found"
  fi
}

test_ssh_agent_mgr_cancellation_interactive() {
  local test_tmp_dir="/tmp/catstar_test_agent_mgr_cancel_$$"
  local mock_bin_dir="$test_tmp_dir/bin"
  mkdir -p "$mock_bin_dir"

  cat << 'EOF' > "$mock_bin_dir/ssh-add"
#!/bin/sh
if [ "$1" = "-l" ]; then
  echo "2048 SHA256:mockfingerprint mock_key_comment (ED25519)"
  exit 0
fi
exit 1
EOF
  chmod +x "$mock_bin_dir/ssh-add"

  local mock_sock="$test_tmp_dir/agent.1001"
  python3 -c "import socket; s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.bind('$mock_sock')"

  local output status_code
  output=$(
    export PATH="$mock_bin_dir:$PATH"
    export SSH_AUTH_SOCK="$mock_sock"
    typeset -g -A _CATSTAR_KNOWN_SSH_SOCKETS=()
    print "q" | ssh-agent-mgr 2>&1
  )
  status_code=$?

  rm -rf "$test_tmp_dir"
  assert_eq "$status_code" "0" "Cancelling selection ('q') should exit with code 0"
  expect_contains "$output" "Operation cancelled"
}

test_ssh_agent_mgr_valid_selection() {
  local test_tmp_dir="/tmp/catstar_test_agent_mgr_select_$$"
  local mock_bin_dir="$test_tmp_dir/bin"
  mkdir -p "$mock_bin_dir"

  cat << 'EOF' > "$mock_bin_dir/ssh-add"
#!/bin/sh
if [ "$1" = "-l" ]; then
  echo "2048 SHA256:mockfingerprint test_user@host (RSA)"
  exit 0
fi
exit 1
EOF
  chmod +x "$mock_bin_dir/ssh-add"

  local mock_sock="$test_tmp_dir/agent.2002"
  python3 -c "import socket; s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.bind('$mock_sock')"

  local output status_code
  output=$(
    export PATH="$mock_bin_dir:$PATH"
    export SSH_AUTH_SOCK=""
    typeset -g -A _CATSTAR_KNOWN_SSH_SOCKETS=("$mock_sock" 1)
    print "1" | ssh-agent-mgr 2>&1
  )
  status_code=$?

  rm -rf "$test_tmp_dir"
  assert_eq "$status_code" "0" "Selecting valid agent should succeed with code 0"
  expect_contains "$output" "Successfully switched SSH_AUTH_SOCK to:"
}

test_ssh_agent_mgr_invalid_selection() {
  local test_tmp_dir="/tmp/catstar_test_agent_mgr_invalid_$$"
  local mock_bin_dir="$test_tmp_dir/bin"
  mkdir -p "$mock_bin_dir"

  cat << 'EOF' > "$mock_bin_dir/ssh-add"
#!/bin/sh
if [ "$1" = "-l" ]; then
  echo "2048 SHA256:mockfingerprint test_user@host (RSA)"
  exit 0
fi
exit 1
EOF
  chmod +x "$mock_bin_dir/ssh-add"

  local mock_sock="$test_tmp_dir/agent.3003"
  python3 -c "import socket; s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.bind('$mock_sock')"

  local output status_code
  output=$(
    export PATH="$mock_bin_dir:$PATH"
    export SSH_AUTH_SOCK="$mock_sock"
    typeset -g -A _CATSTAR_KNOWN_SSH_SOCKETS=()
    print "99" | ssh-agent-mgr 2>&1
  )
  status_code=$?

  rm -rf "$test_tmp_dir"
  assert_eq "$status_code" "1" "Invalid choice '99' should exit with status 1"
  expect_contains "$output" "Invalid selection: 99"
}
