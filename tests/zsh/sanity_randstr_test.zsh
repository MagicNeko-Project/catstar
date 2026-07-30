# Sanity Unit Tests for randstr and Utility Functions
# -----------------------------------------------------------------------------

describe "RandStrTest"

test_randstr_default_length_and_format() {
  local res
  res=$(randstr)
  assert_eq "$?" "0" "randstr should execute cleanly"
  expect_eq "${#res}" "16" "Default randstr length should be 16"
  expect_match "^[0-9a-z]{16}$" "$res" "Default randstr charset should be 0-9a-z"
}

test_randstr_custom_length_and_charset() {
  local res
  res=$(randstr "0-9" "32")
  assert_eq "$?" "0"
  expect_eq "${#res}" "32" "Custom length should be 32"
  expect_match "^[0-9]{32}$" "$res" "Charset '0-9' should yield numeric string"
}

test_randstr_multiple_count_generation() {
  local res
  res=$(randstr "a-z" "8" "3")
  local -a lines=( ${(f)res} )
  expect_eq "${#lines}" "3" "randstr with count 3 should generate 3 lines"
  expect_match "^[a-z]{8}$" "${lines[1]}"
  expect_match "^[a-z]{8}$" "${lines[2]}"
  expect_match "^[a-z]{8}$" "${lines[3]}"
}

test_randstr_utility_shortcuts() {
  local num hex_val alpha_val
  num=$(rn "10")
  hex_val=$(rh "8")
  alpha_val=$(rl "12")

  expect_eq "${#num}" "10"
  expect_match "^[0-9]{10}$" "$num"

  expect_eq "${#hex_val}" "8"
  expect_match "^[0-9a-f]{8}$" "$hex_val"

  expect_eq "${#alpha_val}" "12"
  expect_match "^[a-z]{12}$" "$alpha_val"
}
