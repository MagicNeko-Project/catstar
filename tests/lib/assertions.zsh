# Assertion and expectation primitives for ztest.

zmodload -i zsh/datetime

typeset -g _ZTEST_CURRENT_SUITE="Default"
typeset -g _ZTEST_RESULT_FILE=""
typeset -g _ZTEST_OUTPUT_FILE=""

describe() {
  _ZTEST_CURRENT_SUITE="$1"
}

_ztest_log_failure() {
  setopt localoptions noksharrays
  local msg="$1"
  local frame_idx=2

  if [[ "${funcstack[3]:-}" == assert_* ]]; then
    frame_idx=3
  fi

  local location="${funcfiletrace[$frame_idx]:-unknown:0}"

  if [[ -n "$_ZTEST_RESULT_FILE" && -f "$_ZTEST_RESULT_FILE" ]]; then
    print -r -N -- "FAIL|${location}|${msg}" >>! "$_ZTEST_RESULT_FILE"
  else
    print -u2 -r -- "${location}: Failure: ${msg}"
  fi
}

expect_eq() {
  setopt localoptions noksharrays
  local actual="$1"
  local expected="$2"
  local user_msg="${3:-}"

  if [[ "$actual" != "$expected" ]]; then
    local detail="Expected equality of values:
    Expected: \"${expected}\"
      Actual: \"${actual}\""
    [[ -n "$user_msg" ]] && detail="${user_msg}
${detail}"
    _ztest_log_failure "$detail"
    return 1
  fi
  return 0
}

expect_ne() {
  setopt localoptions noksharrays
  local val1="$1"
  local val2="$2"
  local user_msg="${3:-}"

  if [[ "$val1" == "$val2" ]]; then
    local detail="Expected values to be unequal, but both are: \"${val1}\""
    [[ -n "$user_msg" ]] && detail="${user_msg}
${detail}"
    _ztest_log_failure "$detail"
    return 1
  fi
  return 0
}

expect_match() {
  setopt localoptions noksharrays
  local pattern="$1"
  local val="$2"
  local user_msg="${3:-}"

  if [[ ! "$val" =~ $pattern ]]; then
    local detail="Expected match for pattern:
    Pattern: \"${pattern}\"
     Actual: \"${val}\""
    [[ -n "$user_msg" ]] && detail="${user_msg}
${detail}"
    _ztest_log_failure "$detail"
    return 1
  fi
  return 0
}

expect_contains() {
  setopt localoptions noksharrays
  local str="$1"
  local substring="$2"
  local user_msg="${3:-}"

  if [[ "$str" != *"$substring"* ]]; then
    local detail="Expected string to contain substring:
   Substring: \"${substring}\"
    Full Str: \"${str}\""
    [[ -n "$user_msg" ]] && detail="${user_msg}
${detail}"
    _ztest_log_failure "$detail"
    return 1
  fi
  return 0
}

expect_status() {
  local actual_status="$?"
  setopt localoptions noksharrays
  local expected_status="$1"
  local user_msg="${2:-}"

  if [[ "$actual_status" -ne "$expected_status" ]]; then
    local detail="Expected exit status:
    Expected: ${expected_status}
      Actual: ${actual_status}"
    [[ -n "$user_msg" ]] && detail="${user_msg}
${detail}"
    _ztest_log_failure "$detail"
    return 1
  fi
  return 0
}

assert_eq() {
  expect_eq "$@" || exit 1
}

assert_ne() {
  expect_ne "$@" || exit 1
}

assert_match() {
  expect_match "$@" || exit 1
}

assert_contains() {
  expect_contains "$@" || exit 1
}

assert_status() {
  local actual_status="$?"
  setopt localoptions noksharrays
  expect_status "$actual_status" "$@" || exit 1
}
