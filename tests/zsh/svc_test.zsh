# Behavioral tests for svc, the service manager front end
# -----------------------------------------------------------------------------

describe "SvcTest"

typeset -g TEST_WORKSPACE_DIR=""
typeset -g STUB_BIN_DIR=""
typeset -g CALL_LOG=""
typeset -g SUPERVISOR_CONFIG=""
typeset -g INCLUDE_DIR=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/svc_test_XXXXXX")"
  STUB_BIN_DIR="$TEST_WORKSPACE_DIR/bin"
  CALL_LOG="$TEST_WORKSPACE_DIR/calls"
  mkdir -p "$STUB_BIN_DIR"

  # svc enable and disable manage links with the real ln and rm.
  ln -s "${commands[ln]}" "$STUB_BIN_DIR/ln"
  ln -s "${commands[rm]}" "$STUB_BIN_DIR/rm"

  export XDG_CONFIG_HOME="$TEST_WORKSPACE_DIR/config"
  SUPERVISOR_CONFIG="$XDG_CONFIG_HOME/supervisor/supervisord.conf"
  INCLUDE_DIR="$XDG_CONFIG_HOME/supervisor/conf.d"
  unset SVC_BACKEND STUB_EXIT_STATUS
}

TearDown() {
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

# Restricts PATH to recording stand-ins for the given commands, so call this after any setup
# that needs other programs. Each stand-in appends "NAME ARGS" to CALL_LOG.
use_stub_commands() {
  local command_name
  for command_name in "$@"; do
    cat > "$STUB_BIN_DIR/$command_name" <<EOF
#!/bin/sh
printf '%s\\n' "$command_name \$*" >> "$CALL_LOG"
exit \${STUB_EXIT_STATUS:-0}
EOF
    chmod +x "$STUB_BIN_DIR/$command_name"
  done
  PATH="$STUB_BIN_DIR"
  rehash
}

create_supervisor_user_config() {
  mkdir -p "$INCLUDE_DIR"
  print -r -- "[include]
files = %(here)s/conf.d/*.conf" > "$SUPERVISOR_CONFIG"
}

recorded_calls() {
  [[ -f "$CALL_LOG" ]] && print -r -- "$(<"$CALL_LOG")"
}

# --- systemd ---

test_systemd_lists_services_without_a_verb() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl

  svc 2>/dev/null

  expect_eq "$(recorded_calls)" "systemctl list-units --type=service"
}

test_systemd_runs_read_only_verbs_unprivileged() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc status nginx 2>/dev/null
  svc list-timers --all 2>/dev/null
  svc --failed 2>/dev/null

  expect_eq "$(recorded_calls)" "systemctl status nginx
systemctl list-timers --all
systemctl --failed"
}

test_systemd_runs_state_changes_through_sudo() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc restart nginx 2>/dev/null
  svc mask legacy-daemon 2>/dev/null

  # Root runs systemctl directly; everyone else goes through sudo.
  local privilege_prefix="sudo "
  (( EUID == 0 )) && privilege_prefix=""
  expect_eq "$(recorded_calls)" "${privilege_prefix}systemctl restart nginx
${privilege_prefix}systemctl mask legacy-daemon"
}

test_systemd_user_scope_never_uses_sudo() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc --user restart app 2>/dev/null
  svc restart --user app 2>/dev/null

  expect_eq "$(recorded_calls)" "systemctl --user restart app
systemctl --user restart app"
}

test_systemd_logs_read_the_journal() {
  export SVC_BACKEND=systemd
  use_stub_commands journalctl

  svc logs nginx 2>/dev/null
  svc logs -f nginx -n 20 2>/dev/null
  svc logs nginx --follow 2>/dev/null
  svc logs 2>/dev/null
  svc --user logs -f app 2>/dev/null

  expect_eq "$(recorded_calls)" "journalctl -e -u nginx
journalctl -f -u nginx -n 20
journalctl -f -u nginx
journalctl -e
journalctl --user -f -u app"
}

test_svc_returns_the_native_exit_status() {
  export SVC_BACKEND=systemd STUB_EXIT_STATUS=3
  use_stub_commands systemctl

  svc status nginx 2>/dev/null
  expect_status 3 "svc must return the exit status of the command it ran"
}

test_svc_prints_the_native_command_on_stderr() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl
  local stderr_file="$TEST_WORKSPACE_DIR/stderr"

  svc status 'web app' 2>"$stderr_file"

  expect_eq "$(<"$stderr_file")" "+ systemctl status 'web app'"
}

# --- supervisor ---

test_supervisor_is_detected_when_systemd_is_unavailable() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  svc 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG status"
}

test_supervisor_passes_verbs_through_with_the_user_config() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  svc restart web 2>/dev/null
  svc daemon-reload 2>/dev/null
  svc avail 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG restart web
supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG avail"
}

test_supervisor_logs_use_tail_and_maintail() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  svc logs web 2>/dev/null
  svc logs -f web stderr 2>/dev/null
  svc logs -f 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG tail web
supervisorctl -c $SUPERVISOR_CONFIG tail -f web stderr
supervisorctl -c $SUPERVISOR_CONFIG maintail -f"
}

test_supervisor_refuses_reload_and_user_scope() {
  create_supervisor_user_config
  use_stub_commands supervisorctl
  local stderr_file="$TEST_WORKSPACE_DIR/stderr"

  svc reload web 2>"$stderr_file"
  expect_status 1 "reload would restart every program, so svc must refuse it"
  expect_contains "$(<"$stderr_file")" "svc restart NAME"

  svc --user status 2>/dev/null
  expect_status 1 "supervisor has no user manager"

  expect_eq "$(recorded_calls)" "" "Refused requests must not reach supervisorctl"
}

test_supervisor_without_user_config_uses_its_default_config_search() {
  use_stub_commands supervisorctl

  svc status web 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl status web"
}

test_supervisor_enable_links_the_program_file_and_applies() {
  create_supervisor_user_config
  local program_file="$TEST_WORKSPACE_DIR/supervisor.conf"
  print -r -- "[program:web-app]
command=/bin/true" > "$program_file"
  use_stub_commands supervisorctl

  svc enable "$program_file" 2>/dev/null
  expect_status 0
  svc enable --now "$program_file" 2>/dev/null
  expect_status 0 "Enabling an enabled program must succeed"

  local link_path="$INCLUDE_DIR/web-app.conf"
  assert_eq "${link_path:A}" "${program_file:A}" "conf.d must link to the program file under its program name"
  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG update"
}

test_supervisor_enable_names_the_link_after_a_file_without_program_section() {
  create_supervisor_user_config
  local program_file="$TEST_WORKSPACE_DIR/workers.conf"
  print -r -- "[group:workers]" > "$program_file"
  use_stub_commands supervisorctl

  svc enable "$program_file" 2>/dev/null

  local link_path="$INCLUDE_DIR/workers.conf"
  expect_eq "${link_path:A}" "${program_file:A}" "The link must take the file name when no program is named"
}

test_supervisor_enable_never_overwrites_an_existing_config() {
  create_supervisor_user_config
  print -r -- "hand-written" > "$INCLUDE_DIR/web-app.conf"
  local program_file="$TEST_WORKSPACE_DIR/supervisor.conf"
  print -r -- "[program:web-app]" > "$program_file"
  use_stub_commands supervisorctl

  svc enable "$program_file" 2>/dev/null
  expect_status 1

  expect_eq "$(<"$INCLUDE_DIR/web-app.conf")" "hand-written" "The existing config must stay untouched"
  expect_eq "$(recorded_calls)" "" "Nothing must be applied after a refused enable"
}

test_supervisor_disable_removes_only_links_and_applies() {
  create_supervisor_user_config
  local program_file="$TEST_WORKSPACE_DIR/supervisor.conf"
  print -r -- "[program:web-app]" > "$program_file"
  print -r -- "[program:hand-written]" > "$INCLUDE_DIR/hand-written.conf"
  use_stub_commands supervisorctl
  svc enable "$program_file" 2>/dev/null

  svc disable web-app 2>/dev/null
  expect_status 0
  svc disable hand-written 2>/dev/null
  expect_status 1 "Regular files in conf.d were not created by svc enable"

  [[ ! -L "$INCLUDE_DIR/web-app.conf" ]]
  expect_status 0 "The program link must be gone"
  [[ -f "$INCLUDE_DIR/hand-written.conf" ]]
  expect_status 0 "The hand-written config must remain"
  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG update"
}

# --- detection and help ---

test_reports_when_no_service_manager_is_running() {
  use_stub_commands
  local stderr_file="$TEST_WORKSPACE_DIR/stderr"

  svc status web 2>"$stderr_file"

  expect_status 1
  expect_contains "$(<"$stderr_file")" "no supported service manager is running here"
}

test_rejects_an_unknown_backend_override() {
  export SVC_BACKEND=launchd
  use_stub_commands systemctl supervisorctl
  local stderr_file="$TEST_WORKSPACE_DIR/stderr"

  svc status web 2>"$stderr_file"

  expect_status 1
  expect_contains "$(<"$stderr_file")" "unknown SVC_BACKEND 'launchd'"
  expect_eq "$(recorded_calls)" ""
}

test_help_names_the_service_manager_in_use() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  local help_output
  help_output="$(svc help)"

  expect_contains "$help_output" "Usage: svc"
  expect_contains "$help_output" "Service manager: supervisor"
  expect_eq "$(recorded_calls)" "" "help must not run the service manager"
}
