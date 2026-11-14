# Service Management
# -----------------------------------------------------------------------------
# svc drives the host's service manager with one set of systemctl-style verbs:
#
#   svc                            list services
#   svc VERB [NAME...]             status, start, stop, restart, enable, disable, daemon-reload, ...
#   svc logs [-f] [NAME] [ARG...]  recent log entries, or follow them with -f
#   svc --user ...                 systemd's per-user manager instead of the system one
#   svc help                       usage and the service manager in use
#
# Verbs reach the native tool unchanged unless a backend translates them, and every call prints
# the native command before running it.
#
# Backends
#   svc uses the first backend in _svc_backends whose _is_active check succeeds; SVC_BACKEND=<name>
#   skips detection. Supporting another service manager means adding its name to _svc_backends
#   and defining these functions for it:
#
#     _svc_<name>_is_active                      succeed when <name> manages services on this host
#     _svc_<name>_supports_scope SCOPE           succeed when SCOPE ("system" or "user") exists
#     _svc_<name>_run SCOPE [VERB [ARG...]]      run VERB, or list services when VERB is omitted
#     _svc_<name>_logs SCOPE MODE NAME [ARG...]  show logs; MODE is "recent" or "follow", and an
#                                                empty NAME means the manager's own log
#     _svc_<name>_complete                       complete the words after "svc" (words, CURRENT)
# -----------------------------------------------------------------------------

# Service managers in detection order.
typeset -ga _svc_backends=(systemd supervisor)

# --- Entry Point ---

svc() {
  emulate -L zsh

  # Like systemctl, svc accepts --user anywhere on the command line.
  local scope=system
  if (( ${argv[(Ie)--user]} )); then
    scope=user
    argv=("${(@)argv:#--user}")
  fi

  local backend=""
  if _svc_resolve_backend; then
    backend=$REPLY
  fi

  if [[ $1 == (help|-h|--help) ]]; then
    _svc_print_help "$backend"
    return 0
  fi

  if [[ -z $backend ]]; then
    _svc_report_unresolved_backend
    return 1
  fi

  if ! _svc_${backend}_supports_scope "$scope"; then
    print -u2 -r -- "svc: $backend has no $scope services"
    return 1
  fi

  if [[ $1 == logs ]]; then
    shift
    _svc_logs "$backend" "$scope" "$@"
    return
  fi

  _svc_${backend}_run "$scope" "$@"
}

# --- Shared Plumbing ---

# Sets REPLY to the backend in charge: SVC_BACKEND when set, else the first active one.
_svc_resolve_backend() {
  if [[ -n $SVC_BACKEND ]]; then
    REPLY=$SVC_BACKEND
    (( ${_svc_backends[(Ie)$SVC_BACKEND]} ))
    return
  fi

  local backend
  for backend in "${_svc_backends[@]}"; do
    if _svc_${backend}_is_active; then
      REPLY=$backend
      return 0
    fi
  done
  return 1
}

_svc_report_unresolved_backend() {
  if [[ -n $SVC_BACKEND ]]; then
    print -u2 -r -- "svc: unknown SVC_BACKEND '$SVC_BACKEND' (supported: ${(j:, :)_svc_backends})"
    return
  fi
  print -u2 -r -- "svc: no supported service manager is running here (checked: ${(j:, :)_svc_backends})"
}

# Parses "svc logs [-f] [NAME] [ARG...]": -f/--follow may appear anywhere, NAME is the first
# remaining word unless it is an option, and the rest reaches the backend's log tool unchanged.
_svc_logs() {
  local backend=$1 scope=$2
  shift 2

  local mode=recent
  if (( ${argv[(Ie)-f]} || ${argv[(Ie)--follow]} )); then
    mode=follow
    argv=("${(@)argv:#(-f|--follow)}")
  fi

  local name=""
  if [[ -n $1 && $1 != -* ]]; then
    name=$1
    shift
  fi

  _svc_${backend}_logs "$scope" "$mode" "$name" "$@"
}

_svc_print_help() {
  local backend=$1
  print -r -- "Usage: svc [--user] [VERB [ARG...]]

  svc                            list services
  svc status|start|stop|restart NAME...
  svc logs [-f] [NAME] [ARG...]  recent log entries, -f to follow; without NAME, the manager's log
  svc enable FILE|NAME...        start at boot (supervisor: link a program file into conf.d)
  svc disable NAME...            stop starting at boot (supervisor: remove that link)
  svc daemon-reload              apply changed service definitions
  svc VERB [ARG...]              any other verb goes to the service manager unchanged

--user selects systemd's per-user manager. State changes on the system manager run through sudo.
Every call prints the native command before running it.
"
  if [[ -z $backend ]]; then
    _svc_report_unresolved_backend
    return
  fi
  print -r -- "Service manager: $backend (detection order: ${(j:, :)_svc_backends}; SVC_BACKEND overrides)"
}

# Prints the native command on stderr, dimmed on a terminal, so translation and sudo stay visible,
# then runs it and returns its status.
_svc_run() {
  local command_text="+ ${(j: :)${(q-)@}}"
  if [[ -t 2 ]]; then
    print -u2 -P -- "%F{8}${command_text//\%/%%}%f"
  else
    print -u2 -r -- "$command_text"
  fi
  "$@"
}

# Runs a command as root: directly when already root, else through sudo when it is installed.
_svc_run_as_root() {
  if (( EUID != 0 )) && (( $+commands[sudo] )); then
    _svc_run sudo "$@"
    return
  fi
  _svc_run "$@"
}

# --- Backend: systemd ---

# /run/systemd/system exists only when systemd booted the host (sd_booted(3)); systemctl alone is
# also installed where systemd is not running, such as most containers.
_svc_systemd_is_active() {
  (( $+commands[systemctl] )) && [[ -d /run/systemd/system ]]
}

_svc_systemd_supports_scope() {
  [[ $1 == (system|user) ]]
}

_svc_systemd_run() {
  local scope=$1
  shift

  local -a systemctl_command=(systemctl)
  if [[ $scope == user ]]; then
    systemctl_command+=(--user)
  fi

  if (( $# == 0 )); then
    _svc_run "${systemctl_command[@]}" list-units --type=service
    return
  fi

  if [[ $scope == system ]] && _svc_systemd_changes_state "$1"; then
    _svc_run_as_root "${systemctl_command[@]}" "$@"
    return
  fi
  _svc_run "${systemctl_command[@]}" "$@"
}

# Read-only verbs run unprivileged; every other verb changes state and needs root on the system
# manager, the same split as Oh My Zsh's systemd plugin. Options alone make systemctl list units.
_svc_systemd_changes_state() {
  local verb=$1
  local -a read_only_verbs=(
    cat get-default is-active is-enabled is-failed is-system-running list-automounts
    list-dependencies list-jobs list-machines list-paths list-sockets list-timers list-unit-files
    list-units show show-environment status
  )
  [[ $verb != -* ]] && (( ! ${read_only_verbs[(Ie)$verb]} ))
}

_svc_systemd_logs() {
  local scope=$1 mode=$2 name=$3
  shift 3

  local -a journalctl_command=(journalctl)
  if [[ $scope == user ]]; then
    journalctl_command+=(--user)
  fi

  # -e opens the pager at the newest entries; following streams new entries instead.
  if [[ $mode == follow ]]; then
    journalctl_command+=(-f)
  else
    journalctl_command+=(-e)
  fi

  if [[ -n $name ]]; then
    journalctl_command+=(-u "$name")
  fi
  _svc_run "${journalctl_command[@]}" "$@"
}

# Completes through systemd's own _systemctl by presenting the words as a systemctl command line,
# with "logs" read as "status" so that unit names complete for it too.
_svc_systemd_complete() {
  words[1]=systemctl
  local word_index
  for (( word_index = 2; word_index < CURRENT; word_index++ )); do
    [[ $words[word_index] == -* ]] && continue
    [[ $words[word_index] == logs ]] && words[word_index]=status
    break
  done
  _normal
}

# --- Backend: supervisor ---

_svc_supervisor_is_active() {
  (( $+commands[supervisorctl] ))
}

# supervisorctl talks to whichever supervisord its config names, so there is no user manager to
# switch to; refusing --user is clearer than silently ignoring it.
_svc_supervisor_supports_scope() {
  [[ $1 == system ]]
}

_svc_supervisor_run() {
  shift  # the scope, always "system"
  _svc_supervisor_command
  local -a supervisorctl_command=("${reply[@]}")

  if (( $# == 0 )); then
    _svc_run "${supervisorctl_command[@]}" status
    return
  fi

  case $1 in
    daemon-reload)
      _svc_supervisor_apply
      ;;
    enable)
      shift
      _svc_supervisor_enable "$@"
      ;;
    disable)
      shift
      _svc_supervisor_disable "$@"
      ;;
    reload)
      # "supervisorctl reload" restarts supervisord and every program without asking.
      print -u2 -r -- "svc: supervisor cannot reload a single program; use 'svc restart NAME'"
      return 1
      ;;
    *)
      _svc_run "${supervisorctl_command[@]}" "$@"
      ;;
  esac
}

_svc_supervisor_logs() {
  local mode=$2 name=$3  # $1 is the scope, always "system"
  shift 3

  _svc_supervisor_command
  local -a supervisorctl_command=("${reply[@]}")
  local -a follow_option=()
  if [[ $mode == follow ]]; then
    follow_option=(-f)
  fi

  if [[ -z $name ]]; then
    _svc_run "${supervisorctl_command[@]}" maintail "${follow_option[@]}" "$@"
    return
  fi
  _svc_run "${supervisorctl_command[@]}" tail "${follow_option[@]}" "$name" "$@"
}

# Supervisor reads no config-path environment variable, so a per-user supervisord keeps its config
# at this XDG path; without the file, supervisorctl falls back to its own config search.
_svc_supervisor_user_config() {
  REPLY="${XDG_CONFIG_HOME:-$HOME/.config}/supervisor/supervisord.conf"
}

# Sets reply to the supervisorctl command line for the config in use.
_svc_supervisor_command() {
  _svc_supervisor_user_config
  reply=(supervisorctl)
  if [[ -f $REPLY ]]; then
    reply+=(-c "$REPLY")
  fi
}

# Applies config changes: adds new programs, removes dropped ones, restarts changed ones.
_svc_supervisor_apply() {
  _svc_supervisor_command
  _svc_run "${reply[@]}" update
}

# Sets REPLY to the conf.d directory beside the user config, which the conventional
# "[include] files = %(here)s/conf.d/*.conf" line pulls in.
_svc_supervisor_include_directory() {
  _svc_supervisor_user_config
  local config_file=$REPLY
  local include_directory="${config_file:h}/conf.d"
  if [[ ! -f $config_file || ! -d $include_directory ]]; then
    print -u2 -r -- "svc: enable and disable need $config_file and $include_directory"
    return 1
  fi
  REPLY=$include_directory
}

# Sets REPLY to the program a config file defines: its first [program:NAME] section, or the file
# name when it has none.
_svc_supervisor_program_name() {
  local program_file=$1
  local program_section_pattern='^\[program:([^]]+)\]'
  local line
  while IFS= read -r line; do
    if [[ $line =~ $program_section_pattern ]]; then
      REPLY=$match[1]
      return 0
    fi
  done < "$program_file"
  REPLY=${program_file:t:r}
}

# Enabling links a program file into conf.d under its program name, then applies the change; ln
# refuses to replace an existing entry. --now is accepted for systemctl muscle memory, since
# applying starts new programs anyway.
_svc_supervisor_enable() {
  local -a program_files=("${(@)argv:#--now}")
  if (( ${#program_files} == 0 )); then
    print -u2 -r -- "usage: svc enable PROGRAM_FILE..."
    return 1
  fi
  _svc_supervisor_include_directory || return
  local include_directory=$REPLY

  local program_file link_path
  for program_file in "${program_files[@]}"; do
    if [[ ! -f $program_file ]]; then
      print -u2 -r -- "svc: no such program file: $program_file"
      return 1
    fi
    _svc_supervisor_program_name "$program_file"
    link_path="$include_directory/$REPLY.conf"
    if [[ -L $link_path && ${link_path:A} == ${program_file:A} ]]; then
      continue  # already enabled
    fi
    _svc_run ln -s "${program_file:A}" "$link_path" || return
  done
  _svc_supervisor_apply
}

# Disabling removes the links svc enable made, then applies the change, which stops the programs.
# Regular files in conf.d are left alone because svc did not create them.
_svc_supervisor_disable() {
  local -a program_names=("${(@)argv:#--now}")
  if (( ${#program_names} == 0 )); then
    print -u2 -r -- "usage: svc disable PROGRAM..."
    return 1
  fi
  _svc_supervisor_include_directory || return
  local include_directory=$REPLY

  local program_name link_path
  for program_name in "${program_names[@]}"; do
    link_path="$include_directory/$program_name.conf"
    if [[ ! -L $link_path ]]; then
      print -u2 -r -- "svc: $program_name is not enabled through a link in $include_directory"
      return 1
    fi
    _svc_run rm "$link_path" || return
  done
  _svc_supervisor_apply
}

_svc_supervisor_complete() {
  if (( CURRENT == 2 )); then
    local -a supervisor_verbs=(
      'status:show program status'
      'start:start programs'
      'stop:stop programs'
      'restart:restart programs'
      'enable:link a program file into conf.d and apply'
      'disable:remove a program link and apply'
      'daemon-reload:apply configuration changes'
      'avail:list configured programs'
      'reread:reload configuration without applying it'
      'update:apply configuration changes'
      'signal:send a signal to programs'
      'clear:clear program logs'
    )
    _describe -t commands 'svc command' supervisor_verbs
    return
  fi

  local expl
  case $words[2] in
    enable)
      _files
      ;;
    disable)
      _svc_supervisor_include_directory 2>/dev/null || return 1
      local -a linked_programs=("$REPLY"/*.conf(N@:t:r))
      _wanted programs expl 'enabled program' compadd -a linked_programs
      ;;
    *)
      _svc_supervisor_command
      local -a program_names=(${${(f)"$("${reply[@]}" status 2>/dev/null)"}%% *})
      _wanted programs expl 'program' compadd -a program_names
      ;;
  esac
}

# --- Completion ---

_svc() {
  _svc_resolve_backend || return 1
  local backend=$REPLY
  local completion_status=1

  # svc's own verbs join the backend's while the verb itself is being completed.
  local -a words_before_cursor=("${(@)${(@)words[2,CURRENT-1]}:#--user}")
  if (( ${#words_before_cursor} == 0 )); then
    local -a svc_verbs=(
      'logs:show recent log entries (-f follows)'
      'help:show usage and the service manager in use'
    )
    _describe -t svc-commands 'svc command' svc_verbs && completion_status=0
  fi

  _svc_${backend}_complete && completion_status=0
  return $completion_status
}

if (( $+functions[compdef] )); then
  compdef _svc svc
fi
