# Subshell test execution, microsecond timing, and mktemp IPC for ztest.

_ztest_init_ipc() {
  _ZTEST_RESULT_FILE="$(mktemp "${TMPDIR:-/tmp}/ztest_res_XXXXXX")"
  _ZTEST_OUTPUT_FILE="$(mktemp "${TMPDIR:-/tmp}/ztest_out_XXXXXX")"
}

_ztest_cleanup_ipc() {
  [[ -n "$_ZTEST_RESULT_FILE" && -f "$_ZTEST_RESULT_FILE" ]] && rm -f "$_ZTEST_RESULT_FILE"
  [[ -n "$_ZTEST_OUTPUT_FILE" && -f "$_ZTEST_OUTPUT_FILE" ]] && rm -f "$_ZTEST_OUTPUT_FILE"
}

ztest_execute_single_test() {
  setopt localoptions noksharrays
  local run_k="$1"
  local fn_name="${TEST_FUNCS[$run_k]}"

  : >! "$_ZTEST_RESULT_FILE"
  : >! "$_ZTEST_OUTPUT_FILE"

  typeset -g TEST_DURATION_MS=0
  typeset -g TEST_SUBSHELL_STATUS=0
  typeset -ga TEST_FAILURES=()

  local test_start_time=$EPOCHREALTIME

  (
    local src_file="${TEST_FILE_PATHS[$run_k]}"
    [[ -f "$src_file" ]] && source "$src_file"
    if (( $+functions[TearDown] )); then trap 'TearDown' EXIT; fi
    if (( $+functions[SetUp] )); then SetUp || exit 1; fi
    "$fn_name"
  ) >! "$_ZTEST_OUTPUT_FILE" 2>&1
  TEST_SUBSHELL_STATUS=$?

  local test_end_time=$EPOCHREALTIME
  TEST_DURATION_MS=$(( (test_end_time - test_start_time) * 1000 ))

  if [[ -s "$_ZTEST_RESULT_FILE" ]]; then
    TEST_FAILURES=( ${(0)"$(<$_ZTEST_RESULT_FILE)"} )
  fi
}
