# ANSI color formatting and progress reporting for ztest.

ztest_init_colors() {
  setopt localoptions noksharrays
  typeset -g C_RESET="" C_GREEN="" C_RED="" C_YELLOW="" C_CYAN=""
  if [[ "$ZTEST_USE_COLOR" == "yes" || ( "$ZTEST_USE_COLOR" == "auto" && -t 1 ) ]]; then
    C_RESET=$'\e[0m'
    C_GREEN=$'\e[32m'
    C_RED=$'\e[31m'
    C_YELLOW=$'\e[33m'
    C_CYAN=$'\e[36m'
  fi
}

ztest_report_header() {
  print "${C_GREEN}[==========]${C_RESET} Running ${1} tests from ${2} test suites."
  print "${C_GREEN}[----------]${C_RESET} Global test environment set-up."
}

ztest_report_suite_start() {
  print "${C_GREEN}[----------]${C_RESET} ${2} tests from ${1}"
}

ztest_report_test_start() {
  print "${C_GREEN}[ RUN      ]${C_RESET} ${1}"
}

ztest_report_test_ok() {
  printf "${C_GREEN}[       OK ]${C_RESET} %s (%.2f ms)\n" "$1" "$2"
}

ztest_report_test_fail() {
  printf "${C_RED}[  FAILED  ]${C_RESET} %s (%.2f ms)\n" "$1" "$2"

  if (( ${#TEST_FAILURES} > 0 )); then
    local fail_line=""
    for fail_line in "${(@)TEST_FAILURES}"; do
      local f_body="${fail_line#FAIL|}"
      local f_loc="${f_body%%|*}"
      local f_msg="${f_body#*|}"
      print -u2 "${C_RED}${f_loc}: Failure${C_RESET}"
      print -u2 "${f_msg}"
    done
  elif (( TEST_SUBSHELL_STATUS != 0 )); then
    print -u2 "${C_RED}${1}: Failure - Subshell exited with status ${TEST_SUBSHELL_STATUS}${C_RESET}"
  fi

  if [[ -s "$_ZTEST_OUTPUT_FILE" ]]; then
    print -u2 "${C_YELLOW}--- Captured Test Output ---${C_RESET}"
    cat "$_ZTEST_OUTPUT_FILE" >&2
    print -u2 "${C_YELLOW}----------------------------${C_RESET}"
  fi
}

ztest_report_suite_end() {
  printf "${C_GREEN}[----------]${C_RESET} %d tests from %s (%.2f ms total)\n\n" "$2" "$1" "$3"
}

ztest_report_summary() {
  print "${C_GREEN}[----------]${C_RESET} Global test environment tear-down."
  printf "${C_GREEN}[==========]${C_RESET} %d tests from %d test suites ran. (%.2f ms total)\n" "$1" "$2" "$3"

  if (( $4 > 0 )); then
    print "${C_GREEN}[  PASSED  ]${C_RESET} ${4} tests."
  fi

  if (( $5 > 0 )); then
    print "${C_RED}[  FAILED  ]${C_RESET} ${5} tests, listed below:"
    local f_k=""
    for f_k in "${@[6,-1]}"; do
      print "${C_RED}[  FAILED  ]${C_RESET} ${f_k}"
    done
    print
    print "${C_RED} ${5} FAILED TEST(S)${C_RESET}"
  fi
}
