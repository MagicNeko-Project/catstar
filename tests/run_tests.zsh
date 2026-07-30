#!/usr/bin/env zsh
# Test runner script for discovering and executing ztest suites.

() {
  setopt localoptions noksharrays

  local script_path="${(%):-%x}"
  typeset -g TEST_DIR="${script_path:a:h}"

  local engine_script=""
  if [[ -f "$TEST_DIR/lib/ztest.zsh" ]]; then
    engine_script="$TEST_DIR/lib/ztest.zsh"
  elif [[ -f "$TEST_DIR/zsh/ztest.zsh" ]]; then
    engine_script="$TEST_DIR/zsh/ztest.zsh"
  elif [[ -f "$TEST_DIR/ztest.zsh" ]]; then
    engine_script="$TEST_DIR/ztest.zsh"
  fi

  if [[ -z "$engine_script" ]]; then
    print -u2 "Error: ztest.zsh not found in $TEST_DIR"
    return 1
  fi
  source "$engine_script"

  local filter_pattern="*"
  local list_tests=false
  local break_on_failure=false
  local use_color="auto"
  local custom_bootstrap=""
  local -a test_files=()

  while (( $# > 0 )); do
    case "$1" in
      --bootstrap=*)
        custom_bootstrap="${1#*=}"
        shift
        ;;
      --bootstrap)
        custom_bootstrap="$2"
        shift 2
        ;;
      --filter=*|-f=*)
        filter_pattern="${1#*=}"
        shift
        ;;
      --filter|-f)
        filter_pattern="$2"
        shift 2
        ;;
      --list|-l)
        list_tests=true
        shift
        ;;
      --break-on-failure|-b)
        break_on_failure=true
        shift
        ;;
      --color=*)
        use_color="${1#*=}"
        shift
        ;;
      --color)
        use_color="$2"
        shift 2
        ;;
      --help|-h)
        print "Usage: ./run_tests.zsh [options] [test_files...]"
        print "Options:"
        print "  -f, --filter PATTERN        Run only tests matching PATTERN"
        print "  -l, --list                  List discovered tests without running"
        print "  -b, --break-on-failure      Stop execution on first failed test"
        print "      --bootstrap PATH        Specify a bootstrap script to load environment"
        print "      --color=yes|no|auto    Control ANSI colored output"
        print "  -h, --help                  Show this help menu"
        return 0
        ;;
      *)
        if [[ -f "$1" ]]; then
          test_files+=("${1:a}")
        fi
        shift
        ;;
    esac
  done

  local bootstrap_script="${custom_bootstrap:-${ZTEST_BOOTSTRAP:-}}"
  if [[ -z "$bootstrap_script" && -f "$TEST_DIR/bootstrap.zsh" ]]; then
    bootstrap_script="$TEST_DIR/bootstrap.zsh"
  fi

  if [[ -n "$bootstrap_script" && -f "$bootstrap_script" ]]; then
    source "$bootstrap_script"
  fi

  if (( ${#test_files} == 0 )); then
    test_files=( "$TEST_DIR"/**/*_test.zsh(N) "$TEST_DIR"/*_test.zsh(N) )
    typeset -aU test_files
  fi

  if (( ${#test_files} == 0 )); then
    print -u2 "No test files found in $TEST_DIR"
    return 1
  fi

  local c_reset="" c_green="" c_red="" c_yellow="" c_cyan=""
  if [[ "$use_color" == "yes" || ( "$use_color" == "auto" && -t 1 ) ]]; then
    c_reset=$'\e[0m'
    c_green=$'\e[32m'
    c_red=$'\e[31m'
    c_yellow=$'\e[33m'
    c_cyan=$'\e[36m'
  fi

  typeset -A TEST_FUNCS
  typeset -A TEST_SUITES
  typeset -A TEST_FILE_PATHS
  typeset -a DISCOVERED_TEST_KEYS=()

  local t_file="" fn_item=""
  for t_file in "${test_files[@]}"; do
    local -a funcs_before=() funcs_after=() new_funcs=()
    funcs_before=( ${(k)functions} )

    _ZTEST_CURRENT_SUITE="${t_file:t:r}"
    source "$t_file"

    funcs_after=( ${(k)functions} )
    new_funcs=( ${funcs_after:|funcs_before} )

    for fn_item in "${new_funcs[@]}"; do
      if [[ "$fn_item" == test_* || "$fn_item" == test:* ]]; then
        local s_name="$_ZTEST_CURRENT_SUITE"
        local t_name="$fn_item"

        if [[ "$fn_item" == test:* ]]; then
          local parts=( ${(s/:/)fn_item} )
          s_name="${parts[2]}"
          t_name="${parts[3]}"
        elif [[ "$fn_item" == test_* ]]; then
          t_name="${fn_item#test_}"
        fi

        local t_key="${s_name}.${t_name}"
        TEST_FUNCS[$t_key]="$fn_item"
        TEST_SUITES[$t_key]="$s_name"
        TEST_FILE_PATHS[$t_key]="$t_file"
        DISCOVERED_TEST_KEYS+=("$t_key")
      fi
    done
  done

  if [[ "$list_tests" == true ]]; then
    print "${c_cyan}Discovered Tests:${c_reset}"
    local list_k=""
    for list_k in "${DISCOVERED_TEST_KEYS[@]}"; do
      print "  - $list_k (${TEST_FUNCS[$list_k]})"
    done
    return 0
  fi

  local -a RUN_TEST_KEYS=()
  local filter_k=""
  for filter_k in "${DISCOVERED_TEST_KEYS[@]}"; do
    if [[ "$filter_k" == ${~filter_pattern} || "${TEST_FUNCS[$filter_k]}" == ${~filter_pattern} ]]; then
      RUN_TEST_KEYS+=("$filter_k")
    fi
  done

  if (( ${#RUN_TEST_KEYS} == 0 )); then
    print "${c_yellow}No tests matched filter pattern: '$filter_pattern'${c_reset}"
    return 0
  fi

  typeset -A SUITE_TEST_COUNTS
  typeset -a SUITE_NAMES=()
  local group_k=""
  for group_k in "${RUN_TEST_KEYS[@]}"; do
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

  print "${c_green}[==========]${c_reset} Running ${total_tests} tests from ${total_suites} test suites."
  print "${c_green}[----------]${c_reset} Global test environment set-up."

  local passed_count=0
  local failed_count=0
  local -a failed_test_keys=()

  local cur_suite="" run_k=""
  for cur_suite in "${SUITE_NAMES[@]}"; do
    local suite_count=${SUITE_TEST_COUNTS[$cur_suite]}
    print "${c_green}[----------]${c_reset} ${suite_count} tests from ${cur_suite}"
    local suite_start_time=$EPOCHREALTIME

    for run_k in "${RUN_TEST_KEYS[@]}"; do
      [[ "${TEST_SUITES[$run_k]}" != "$cur_suite" ]] && continue

      local fn_name="${TEST_FUNCS[$run_k]}"
      print "${c_green}[ RUN      ]${c_reset} ${run_k}"

      : >! "$_ZTEST_RESULT_FILE"
      : >! "$_ZTEST_OUTPUT_FILE"

      local test_start_time=$EPOCHREALTIME

      (
        local src_file="${TEST_FILE_PATHS[$run_k]}"
        [[ -f "$src_file" ]] && source "$src_file"
        if (( $+functions[SetUp] )); then SetUp || exit 1; fi
        "$fn_name"
        local ret=$?
        if (( $+functions[TearDown] )); then TearDown; fi
        exit $ret
      ) >! "$_ZTEST_OUTPUT_FILE" 2>&1
      local subshell_status=$?

      local test_end_time=$EPOCHREALTIME
      local duration_ms=$(( (test_end_time - test_start_time) * 1000 ))

      local -a failures=()
      if [[ -s "$_ZTEST_RESULT_FILE" ]]; then
        failures=( ${(0)$(<$_ZTEST_RESULT_FILE)} )
      fi

      if (( ${#failures} == 0 && subshell_status == 0 )); then
        passed_count=$(( passed_count + 1 ))
        printf "${c_green}[       OK ]${c_reset} %s (%.2f ms)\n" "$run_k" "$duration_ms"
      else
        failed_count=$(( failed_count + 1 ))
        failed_test_keys+=("$run_k")
        printf "${c_red}[  FAILED  ]${c_reset} %s (%.2f ms)\n" "$run_k" "$duration_ms"

        if (( ${#failures} > 0 )); then
          local fail_line=""
          for fail_line in "${failures[@]}"; do
            local f_body="${fail_line#FAIL|}"
            local f_loc="${f_body%%|*}"
            local f_msg="${f_body#*|}"
            print -u2 "${c_red}${f_loc}: Failure${c_reset}"
            print -u2 "${f_msg}"
          done
        elif (( subshell_status != 0 )); then
          print -u2 "${c_red}${run_k}: Failure - Subshell exited with status ${subshell_status}${c_reset}"
        fi

        if [[ -s "$_ZTEST_OUTPUT_FILE" ]]; then
          print -u2 "${c_yellow}--- Captured Test Output ---${c_reset}"
          cat "$_ZTEST_OUTPUT_FILE" >&2
          print -u2 "${c_yellow}----------------------------${c_reset}"
        fi

        if [[ "$break_on_failure" == true ]]; then
          print -u2 "${c_red}Stopping test runner due to --break-on-failure flag.${c_reset}"
          break 2
        fi
      fi
    done

    local suite_end_time=$EPOCHREALTIME
    local suite_duration_ms=$(( (suite_end_time - suite_start_time) * 1000 ))
    printf "${c_green}[----------]${c_reset} %d tests from %s (%.2f ms total)\n\n" "$suite_count" "$cur_suite" "$suite_duration_ms"
  done

  local overall_end_time=$EPOCHREALTIME
  local total_duration_ms=$(( (overall_end_time - overall_start_time) * 1000 ))

  print "${c_green}[----------]${c_reset} Global test environment tear-down."
  printf "${c_green}[==========]${c_reset} %d tests from %d test suites ran. (%.2f ms total)\n" "$total_tests" "$total_suites" "$total_duration_ms"

  if (( passed_count > 0 )); then
    print "${c_green}[  PASSED  ]${c_reset} ${passed_count} tests."
  fi

  if (( failed_count > 0 )); then
    print "${c_red}[  FAILED  ]${c_reset} ${failed_count} tests, listed below:"
    local f_k=""
    for f_k in "${failed_test_keys[@]}"; do
      print "${c_red}[  FAILED  ]${c_reset} ${f_k}"
    done
    print
    print "${c_red} ${failed_count} FAILED TEST(S)${c_reset}"
  fi

  _ztest_cleanup_ipc

  (( failed_count > 0 )) && return 1
  return 0
} "$@"
