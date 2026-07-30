# Main entry point for ztest framework modules.

() {
  local lib_dir="${${(%):-%x}:a:h}"
  source "${lib_dir}/assertions.zsh"
  source "${lib_dir}/cli.zsh"
  source "${lib_dir}/discovery.zsh"
  source "${lib_dir}/executor.zsh"
  source "${lib_dir}/reporter.zsh"
}

ztest_main() {
  setopt localoptions noksharrays
  local test_dir="$1"
  shift

  ztest_parse_cli "$@"
  local cli_status=$?
  (( cli_status == 10 )) && return 0
  (( cli_status != 0 )) && return 1

  # Environment Bootstrapping
  local bootstrap_script="${ZTEST_CUSTOM_BOOTSTRAP:-${ZTEST_BOOTSTRAP:-}}"
  if [[ -z "$bootstrap_script" && -f "$test_dir/bootstrap.zsh" ]]; then
    bootstrap_script="$test_dir/bootstrap.zsh"
  fi

  if [[ -n "$bootstrap_script" && -f "$bootstrap_script" ]]; then
    source "$bootstrap_script"
  fi

  ztest_discover_test_files "$test_dir"
  if (( ${#DISCOVERED_FILES} == 0 )); then
    print -u2 "No test files found in $test_dir"
    return 1
  fi

  ztest_init_colors
  ztest_discover_test_funcs

  if [[ "$ZTEST_LIST_TESTS" == true ]]; then
    print "${C_CYAN}Discovered Tests:${C_RESET}"
    local list_k=""
    for list_k in "${(@)DISCOVERED_TEST_KEYS}"; do
      print "  - $list_k (${TEST_FUNCS[$list_k]})"
    done
    return 0
  fi

  local -a RUN_TEST_KEYS=()
  local filter_k=""
  for filter_k in "${(@)DISCOVERED_TEST_KEYS}"; do
    if [[ "$filter_k" == ${~ZTEST_FILTER} || "${TEST_FUNCS[$filter_k]}" == ${~ZTEST_FILTER} ]]; then
      RUN_TEST_KEYS+=("$filter_k")
    fi
  done

  if (( ${#RUN_TEST_KEYS} == 0 )); then
    print "${C_YELLOW}No tests matched filter pattern: '$ZTEST_FILTER'${C_RESET}"
    return 0
  fi

  typeset -A SUITE_TEST_COUNTS
  typeset -a SUITE_NAMES=()
  local group_k=""
  for group_k in "${(@)RUN_TEST_KEYS}"; do
    local grp_suite="${TEST_SUITES[$group_k]}"
    if [[ -z "${SUITE_TEST_COUNTS[$grp_suite]}" ]]; then
      SUITE_NAMES+=("$grp_suite")
      SUITE_TEST_COUNTS[$grp_suite]=1
    else
      SUITE_TEST_COUNTS[$grp_suite]=$(( SUITE_TEST_COUNTS[$grp_suite] + 1 ))
    fi
  done

  _ztest_init_ipc
  trap '_ztest_cleanup_ipc; exit 1' INT TERM HUP

  local total_tests=${#RUN_TEST_KEYS}
  local total_suites=${#SUITE_NAMES}
  local overall_start_time=$EPOCHREALTIME

  ztest_report_header "$total_tests" "$total_suites"

  local passed_count=0
  local failed_count=0
  local -a failed_test_keys=()

  local cur_suite="" run_k=""
  for cur_suite in "${(@)SUITE_NAMES}"; do
    local suite_count=${SUITE_TEST_COUNTS[$cur_suite]}
    ztest_report_suite_start "$cur_suite" "$suite_count"
    local suite_start_time=$EPOCHREALTIME

    for run_k in "${(@)RUN_TEST_KEYS}"; do
      [[ "${TEST_SUITES[$run_k]}" != "$cur_suite" ]] && continue

      ztest_report_test_start "$run_k"
      ztest_execute_single_test "$run_k"

      if (( ${#TEST_FAILURES} == 0 && TEST_SUBSHELL_STATUS == 0 )); then
        passed_count=$(( passed_count + 1 ))
        ztest_report_test_ok "$run_k" "$TEST_DURATION_MS"
      else
        failed_count=$(( failed_count + 1 ))
        failed_test_keys+=("$run_k")
        ztest_report_test_fail "$run_k" "$TEST_DURATION_MS"

        if [[ "$ZTEST_BREAK_ON_FAILURE" == true ]]; then
          print -u2 "${C_RED}Stopping test runner due to --break-on-failure flag.${C_RESET}"
          local suite_end_time=$EPOCHREALTIME
          local suite_duration_ms=$(( (suite_end_time - suite_start_time) * 1000 ))
          ztest_report_suite_end "$cur_suite" "$suite_count" "$suite_duration_ms"
          break 2
        fi
      fi
    done

    local suite_end_time=$EPOCHREALTIME
    local suite_duration_ms=$(( (suite_end_time - suite_start_time) * 1000 ))
    ztest_report_suite_end "$cur_suite" "$suite_count" "$suite_duration_ms"
  done

  local overall_end_time=$EPOCHREALTIME
  local total_duration_ms=$(( (overall_end_time - overall_start_time) * 1000 ))

  ztest_report_summary "$total_tests" "$total_suites" "$total_duration_ms" "$passed_count" "$failed_count" "${(@)failed_test_keys}"

  _ztest_cleanup_ipc
  (( failed_count > 0 )) && return 1
  return 0
}
