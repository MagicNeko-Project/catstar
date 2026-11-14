# Behavioral tests for svc, the service manager front end
# -----------------------------------------------------------------------------

describe "SvcTest"

typeset -g TEST_WORKSPACE_DIR=""
typeset -g STUB_BIN_DIR=""
typeset -g CALL_LOG=""
typeset -g SUPERVISOR_CONFIG=""
typeset -g INCLUDE_DIR=""
typeset -g OLD_HOME=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/svc_test_XXXXXX")"
  STUB_BIN_DIR="$TEST_WORKSPACE_DIR/bin"
  CALL_LOG="$TEST_WORKSPACE_DIR/calls"
  mkdir -p "$STUB_BIN_DIR" "$TEST_WORKSPACE_DIR/home"

  # svc enable and disable manage links with the real ln and rm.
  ln -s "${commands[ln]}" "$STUB_BIN_DIR/ln"
  ln -s "${commands[rm]}" "$STUB_BIN_DIR/rm"

  OLD_HOME="$HOME"
  export HOME="$TEST_WORKSPACE_DIR/home"
  export XDG_CONFIG_HOME="$TEST_WORKSPACE_DIR/config"
  SUPERVISOR_CONFIG="$XDG_CONFIG_HOME/supervisor/supervisord.conf"
  INCLUDE_DIR="$XDG_CONFIG_HOME/supervisor/conf.d"
  unset SVC_BACKEND STUB_EXIT_STATUS STUB_STATUS_OUTPUT STUB_STATUS_EXIT STUB_REQUIRE_USER
}

TearDown() {
  export HOME="$OLD_HOME"
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

# Restricts PATH to recording stand-ins for the given commands, so call this after any setup
# that needs other programs. sudo forwards via exec so privilege escalation exercises real status
# propagation and logs once via the invoked command stub.
use_stub_commands() {
  local zsh_bin="${commands[zsh]}"
  local command_name
  for command_name in "$@"; do
    if [[ $command_name == sudo ]]; then
      cat > "$STUB_BIN_DIR/sudo" <<EOF
#!$zsh_bin
export SVC_TEST_SUDO_PREFIX="sudo "
exec "\$@"
EOF
    else
      cat > "$STUB_BIN_DIR/$command_name" <<EOF
#!$zsh_bin
if [[ "\$1" == status || ( "\$1" == -c && "\$3" == status ) ]] && (( \$+STUB_STATUS_OUTPUT )); then
  print -r -- "\$STUB_STATUS_OUTPUT"
  exit \${STUB_STATUS_EXIT:-0}
fi
if [[ "\$STUB_REQUIRE_USER" == 1 && -z "\$USER" ]]; then
  print -u2 -r -- "USER env missing"
  exit 99
fi
print -r -- "\${SVC_TEST_SUDO_PREFIX}$command_name\${1:+ }\${(j: :)\${(q-)@}}" >> "$CALL_LOG"
exit \${STUB_EXIT_STATUS:-0}
EOF
    fi
    chmod +x "$STUB_BIN_DIR/$command_name"
  done
  PATH="$STUB_BIN_DIR"
  rehash
}

create_supervisor_user_config() {
  local target_config="${1:-$SUPERVISOR_CONFIG}"
  mkdir -p "${target_config:h}/conf.d"
  print -r -- "[include]
files = %(here)s/conf.d/*.conf" > "$target_config"
}

recorded_calls() {
  [[ -f "$CALL_LOG" ]] && print -r -- "$(<"$CALL_LOG")"
}

clear_recorded_calls() {
  : >| "$CALL_LOG"
}

# --- detection and help ---

test_detection_requires_booted_systemd_when_systemctl_exists() {
  create_supervisor_user_config
  use_stub_commands systemctl supervisorctl sudo

  svc status web 2>/dev/null

  if [[ -d /run/systemd/system ]]; then
    expect_eq "$(recorded_calls)" "systemctl status web"
  else
    expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG status web"
  fi
}

test_supervisor_requires_config_or_live_socket_for_detection() {
  use_stub_commands supervisorctl
  local stderr_file="$TEST_WORKSPACE_DIR/stderr"

  svc status web 2>"$stderr_file"

  if [[ -S /run/supervisor.sock || -S /var/run/supervisor.sock ]]; then
    expect_status 0
    expect_eq "$(recorded_calls)" "supervisorctl status web"
  else
    expect_status 1
    expect_contains "$(<"$stderr_file")" "no supported service manager is running here"
    expect_eq "$(recorded_calls)" ""
  fi
}

test_supervisor_falls_back_to_home_config_when_xdg_differs() {
  export XDG_CONFIG_HOME="$TEST_WORKSPACE_DIR/empty-xdg"
  local home_config="$HOME/.config/supervisor/supervisord.conf"
  create_supervisor_user_config "$home_config"
  use_stub_commands supervisorctl

  svc status web 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl -c $home_config status web"
}

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
  expect_eq "$(recorded_calls)" "" "single-word help must not run the service manager"
}

# --- systemd ---

test_systemd_lists_services_without_a_verb() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc 2>/dev/null

  expect_eq "$(recorded_calls)" "systemctl list-units --type=service"
}

test_systemd_runs_read_only_queries_and_help_unprivileged() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc status nginx 2>/dev/null
  svc list-timers --all 2>/dev/null
  svc --failed 2>/dev/null
  svc whoami 2>/dev/null
  svc help nginx 2>/dev/null
  svc restart --help 2>/dev/null
  svc -M worker status nginx 2>/dev/null
  svc --machine worker status nginx 2>/dev/null

  expect_eq "$(recorded_calls)" "systemctl status nginx
systemctl list-timers --all
systemctl --failed
systemctl whoami
systemctl help nginx
systemctl restart --help
systemctl -M worker status nginx
systemctl --machine worker status nginx"
}

test_systemd_elevates_state_changes_even_with_leading_options() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc restart nginx 2>/dev/null
  svc --now enable nginx 2>/dev/null
  svc -s HUP kill nginx 2>/dev/null
  svc -t service mask legacy-daemon 2>/dev/null
  svc -H status restart nginx 2>/dev/null
  svc --host status restart nginx 2>/dev/null

  local privilege_prefix="sudo "
  (( EUID == 0 )) && privilege_prefix=""
  expect_eq "$(recorded_calls)" "${privilege_prefix}systemctl restart nginx
${privilege_prefix}systemctl --now enable nginx
${privilege_prefix}systemctl -s HUP kill nginx
${privilege_prefix}systemctl -t service mask legacy-daemon
${privilege_prefix}systemctl -H status restart nginx
${privilege_prefix}systemctl --host status restart nginx"
}

test_systemd_user_scope_applies_before_double_dash_only() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  svc --user restart app 2>/dev/null
  svc restart --user app 2>/dev/null
  svc show -- --user 2>/dev/null

  expect_eq "$(recorded_calls)" "systemctl --user restart app
systemctl --user restart app
systemctl show -- --user"
}

test_systemd_logs_preserve_options_and_wrap_unit_names() {
  export SVC_BACKEND=systemd
  use_stub_commands journalctl sudo

  svc logs nginx 2>/dev/null
  svc logs -f nginx -n 20 2>/dev/null
  svc logs nginx --follow 2>/dev/null
  svc logs -n 50 --since today nginx 2>/dev/null
  svc logs -fn 20 nginx 2>/dev/null
  svc logs -r nginx 2>/dev/null
  svc logs -b nginx 2>/dev/null
  svc logs -b -1 nginx 2>/dev/null
  svc logs nginx php-fpm 2>/dev/null
  svc logs -.mount 2>/dev/null
  svc logs -- -.mount 2>/dev/null
  svc logs nginx _PID=42 2>/dev/null
  svc logs 2>/dev/null
  svc --user logs -f app 2>/dev/null

  expect_eq "$(recorded_calls)" "journalctl -e -u nginx
journalctl -f -u nginx -n 20
journalctl -u nginx --follow
journalctl -n 50 --since today -u nginx
journalctl -fn 20 -u nginx
journalctl -r -u nginx
journalctl -e -b -u nginx
journalctl -e -b -1 -u nginx
journalctl -e -u nginx -u php-fpm
journalctl -e -u -.mount
journalctl -e -u -.mount
journalctl -e -u nginx _PID=42
journalctl -e
journalctl --user -f -u app"
}

test_svc_propagates_native_exit_status_including_through_sudo() {
  export SVC_BACKEND=systemd STUB_EXIT_STATUS=3
  use_stub_commands systemctl sudo

  svc status nginx 2>/dev/null
  expect_status 3 "unprivileged calls must propagate the native exit status"

  svc restart nginx 2>/dev/null
  expect_status 3 "sudo-elevated calls must propagate the native exit status"
}

test_svc_prints_quoted_command_with_backslashes_intact() {
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo
  local stderr_file="$TEST_WORKSPACE_DIR/stderr"

  svc status 'web app' 2>"$stderr_file"
  expect_eq "$(<"$stderr_file")" "+ systemctl status 'web app'"

  svc status 'dev-disk-by\x2duuid-1234.device' 2>"$stderr_file"
  expect_eq "$(<"$stderr_file")" "+ systemctl status 'dev-disk-by\\x2duuid-1234.device'"
}

test_svc_tty_trace_preserves_backslashes() {
  zmodload zsh/zpty || return 0
  local zsh_bin="${commands[zsh]}"
  export SVC_BACKEND=systemd
  use_stub_commands systemctl sudo

  local pty_script="$TEST_WORKSPACE_DIR/pty_trace.zsh"
  print -r -- "fpath=(${(j: :)${(@q)fpath}})
autoload -Uz svc
PATH=${(q)PATH}
SVC_BACKEND=systemd
svc status 'dev-disk-by\\x2duuid-1234.device' >/dev/null" > "$pty_script"

  zpty svc_trace_pty "$zsh_bin" -f "$pty_script"
  local pty_output="" line
  while zpty -r svc_trace_pty line; do
    pty_output+="$line"
  done
  zpty -d svc_trace_pty 2>/dev/null

  expect_contains "$pty_output" 'dev-disk-by\x2duuid-1234.device'
}

test_svc_preserves_caller_reply_and_exports_user_for_child() {
  create_supervisor_user_config
  use_stub_commands supervisorctl
  export STUB_REQUIRE_USER=1
  unset USER

  REPLY="caller_scalar"
  reply=(caller one)

  svc status web 2>/dev/null
  expect_status 0 "svc must export USER to child processes when unexported"
  expect_eq "$REPLY" "caller_scalar"
  expect_eq "${reply[*]}" "caller one"
  expect_eq "${+USER}" "0" "caller USER presence must not be altered"
}

# --- supervisor ---

test_supervisor_passes_verbs_through_with_the_user_config() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  svc 2>/dev/null
  svc restart web 2>/dev/null
  svc daemon-reload 2>/dev/null
  svc avail 2>/dev/null
  svc help status 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG status
supervisorctl -c $SUPERVISOR_CONFIG restart web
supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG avail
supervisorctl -c $SUPERVISOR_CONFIG help status"
}

test_supervisor_logs_support_maintail_tail_and_byte_counts() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  svc logs web 2>/dev/null
  svc logs -f web stderr 2>/dev/null
  svc logs -100 web 2>/dev/null
  svc logs web -100 2>/dev/null
  svc logs -500 2>/dev/null
  svc logs -f 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG tail web
supervisorctl -c $SUPERVISOR_CONFIG tail -f web stderr
supervisorctl -c $SUPERVISOR_CONFIG tail -100 web
supervisorctl -c $SUPERVISOR_CONFIG tail -100 web
supervisorctl -c $SUPERVISOR_CONFIG maintail -500
supervisorctl -c $SUPERVISOR_CONFIG maintail -f"

  svc logs --invalid-flag web 2>/dev/null
  expect_status 1 "unsupported supervisor log flags must fail before calling supervisorctl"
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

test_supervisor_without_user_config_uses_default_config_search() {
  export SVC_BACKEND=supervisor
  use_stub_commands supervisorctl

  svc status web 2>/dev/null

  expect_eq "$(recorded_calls)" "supervisorctl status web"
}

test_supervisor_enable_links_and_supports_now_in_either_position() {
  create_supervisor_user_config
  local program_file="$TEST_WORKSPACE_DIR/supervisor.conf"
  print -r -- "[program:web-app]
command=/bin/true" > "$program_file"
  use_stub_commands supervisorctl

  svc enable "$program_file" 2>/dev/null
  expect_status 0
  svc enable --now "$program_file" 2>/dev/null
  expect_status 0 "Enabling an already enabled program must succeed and start with --now"
  svc --now enable "$program_file" 2>/dev/null
  expect_status 0

  local link_path="$INCLUDE_DIR/web-app.conf"
  expect_eq "${link_path:A}" "${program_file:A}"
  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG start web-app
supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG start web-app"
}

test_supervisor_enable_names_special_sections_bundles_and_symlinks() {
  zmodload -F zsh/stat b:zstat
  create_supervisor_user_config
  mkdir -p "$TEST_WORKSPACE_DIR/releases/v1"
  ln -s "$TEST_WORKSPACE_DIR/releases/v1" "$TEST_WORKSPACE_DIR/current"

  local fcgi_file="$TEST_WORKSPACE_DIR/current/app.conf"
  printf '[fcgi-program:api]' > "$fcgi_file"

  local group_file="$TEST_WORKSPACE_DIR/workers.conf"
  print -r -- "[group:workers]
programs=w1,w2" > "$group_file"

  local bundle_file="$TEST_WORKSPACE_DIR/suite.conf"
  print -r -- "[program:alpha]
[program:beta]" > "$bundle_file"

  use_stub_commands supervisorctl

  svc enable --now "$fcgi_file" "$group_file" "$bundle_file" 2>/dev/null
  expect_status 0

  local -a api_link_target
  zstat -A api_link_target -L +link "$INCLUDE_DIR/api.conf"
  expect_eq "${api_link_target[1]}" "$TEST_WORKSPACE_DIR/current/app.conf" "symlinks must keep lexical target via :a"
  [[ -L "$INCLUDE_DIR/workers.conf" && -L "$INCLUDE_DIR/suite.conf" ]]
  expect_status 0

  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG update
supervisorctl -c $SUPERVISOR_CONFIG start api 'workers:*' alpha beta"
}

test_supervisor_enable_never_overwrites_and_fails_atomically() {
  create_supervisor_user_config
  print -r -- "hand-written" > "$INCLUDE_DIR/web-app.conf"
  local valid_file="$TEST_WORKSPACE_DIR/valid.conf"
  local conflict_file="$TEST_WORKSPACE_DIR/conflict.conf"
  print -r -- "[program:fresh-app]" > "$valid_file"
  print -r -- "[program:web-app]" > "$conflict_file"
  use_stub_commands supervisorctl

  svc enable "$valid_file" "$conflict_file" 2>/dev/null
  expect_status 1

  [[ ! -L "$INCLUDE_DIR/fresh-app.conf" ]]
  expect_status 0 "failing validation on a later argument must not leave partial links"
  expect_eq "$(<"$INCLUDE_DIR/web-app.conf")" "hand-written"
  expect_eq "$(recorded_calls)" ""
}

test_supervisor_disable_accepts_name_conf_or_file_and_fails_atomically() {
  create_supervisor_user_config
  local app_a="$TEST_WORKSPACE_DIR/a.conf"
  local app_b="$TEST_WORKSPACE_DIR/b.conf"
  local app_c="$TEST_WORKSPACE_DIR/c.conf"
  print -r -- "[program:app-a]" > "$app_a"
  print -r -- "[program:app-b]" > "$app_b"
  print -r -- "[program:app-c]" > "$app_c"
  print -r -- "[program:hand-written]" > "$INCLUDE_DIR/hand-written.conf"
  use_stub_commands supervisorctl
  svc enable "$app_a" "$app_b" "$app_c" 2>/dev/null
  clear_recorded_calls

  svc disable app-a hand-written 2>/dev/null
  expect_status 1 "partial disable with a regular file must fail before unlinking anything"
  [[ -L "$INCLUDE_DIR/app-a.conf" ]]
  expect_status 0
  expect_eq "$(recorded_calls)" ""

  svc disable app-a app-b.conf "$app_c" 2>/dev/null
  expect_status 0

  [[ ! -L "$INCLUDE_DIR/app-a.conf" && ! -L "$INCLUDE_DIR/app-b.conf" && ! -L "$INCLUDE_DIR/app-c.conf" ]]
  expect_status 0
  [[ -f "$INCLUDE_DIR/hand-written.conf" ]]
  expect_status 0
  expect_eq "$(recorded_calls)" "supervisorctl -c $SUPERVISOR_CONFIG update"
}

# --- completion ---

_run_svc_completion_harness() {
  COMPLETED_CANDIDATES=()
  REPLY="sentinel_scalar"
  reply=(sentinel array)

  compadd() {
    local is_array=false
    while [[ $1 == -* ]]; do
      [[ $1 == -a ]] && is_array=true
      if [[ $1 == -- ]]; then
        shift
        break
      fi
      shift
    done
    if [[ $is_array == true ]]; then
      local arr_name=$1
      COMPLETED_CANDIDATES+=("${(@P)arr_name}")
    else
      COMPLETED_CANDIDATES+=("$@")
    fi
  }
  _wanted() {
    shift 3
    "$@"
  }
  _describe() {
    local arr_name=$argv[-1]
    local entry
    for entry in "${(@P)arr_name}"; do
      COMPLETED_CANDIDATES+=("${entry%%:*}")
    done
  }
  _signals() {
    COMPLETED_CANDIDATES+=(TERM HUP)
  }
  _files() {
    COMPLETED_CANDIDATES+=(__FILES__)
  }

  local -a words=("$@")
  local -i CURRENT=${#words}
  _svc
}

test_completion_filters_supervisor_errors_and_follows_subcommand_grammar() {
  create_supervisor_user_config
  use_stub_commands supervisorctl

  local -a COMPLETED_CANDIDATES

  export STUB_STATUS_OUTPUT="unix:///var/run/supervisor.sock no such file"
  export STUB_STATUS_EXIT=4
  _run_svc_completion_harness svc restart ""
  expect_eq "${COMPLETED_CANDIDATES[*]}" "" "exit-4 connection error text must never complete"
  expect_eq "$REPLY" "sentinel_scalar"
  expect_eq "${reply[*]}" "sentinel array"

  export STUB_STATUS_OUTPUT="web   RUNNING   pid 101, uptime 0:01:00
worker   STOPPED   Not started"
  export STUB_STATUS_EXIT=3
  _run_svc_completion_harness svc restart ""
  expect_eq "${COMPLETED_CANDIDATES[*]}" "web worker"

  _run_svc_completion_harness svc logs web ""
  expect_eq "${COMPLETED_CANDIDATES[*]}" "stdout stderr"

  _run_svc_completion_harness svc signal ""
  expect_eq "${COMPLETED_CANDIDATES[*]}" "TERM HUP"

  _run_svc_completion_harness svc daemon-reload ""
  expect_eq "${COMPLETED_CANDIDATES[*]}" ""

  _run_svc_completion_harness svc --user ""
  expect_eq "${COMPLETED_CANDIDATES[*]}" ""
}
