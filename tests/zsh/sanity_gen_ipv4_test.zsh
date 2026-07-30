# Sanity Unit Tests for gen_ipv4 and IPv4 Generation
# -----------------------------------------------------------------------------

describe "IPv4GeneratorTest"

test_gen_ipv4_default_prefix() {
  local ip
  ip=$(gen_ipv4)
  assert_eq "$?" "0" "gen_ipv4 should execute successfully"
  expect_match "^10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$" "$ip" "Default prefix should start with 10."
}

test_gen_ipv4_explicit_subnet_mask_24() {
  local ip
  ip=$(gen_ipv4 "192.168.1.0/24")
  assert_eq "$?" "0"
  expect_match "^192\.168\.1\.[0-9]{1,3}$" "$ip" "Prefix 192.168.1.0/24 should fix first 3 octets"
}

test_gen_ipv4_explicit_subnet_mask_16() {
  local ip
  ip=$(gen_ipv4 "172.16.0.0/16")
  assert_eq "$?" "0"
  expect_match "^172\.16\.[0-9]{1,3}\.[0-9]{1,3}$" "$ip" "Prefix 172.16.0.0/16 should fix first 2 octets"
}

test_gen_ipv4_full_host_mask_32() {
  local ip
  ip=$(gen_ipv4 "1.2.3.4/32")
  assert_eq "$?" "0"
  expect_eq "$ip" "1.2.3.4" "Mask /32 should match prefix exactly"
}

test_gen_ipv4_shortcut_r4() {
  local ip
  ip=$(r4 "10.5.0.0/16")
  assert_eq "$?" "0"
  expect_match "^10\.5\." "$ip" "r4 shortcut should forward prefix arguments"
}

test_gen_ipv4_invalid_subnet_mask_error() {
  local err status_code
  err=$(gen_ipv4 "10.0.0.0/35" 2>&1)
  status_code=$?

  assert_eq "$status_code" "1" "gen_ipv4 should fail on mask > 32"
  expect_contains "$err" "Subnet mask must be between 0 and 32"
}

test_gen_ipv4_invalid_octet_value_error() {
  local err status_code
  err=$(gen_ipv4 "300.0.0.0/8" 2>&1)
  status_code=$?

  assert_eq "$status_code" "1" "gen_ipv4 should fail on octet > 255"
  expect_contains "$err" "out of range"
}

test_gen_ipv4_invalid_characters_error() {
  local err status_code
  err=$(gen_ipv4 "invalid.ip.str/24" 2>&1)
  status_code=$?

  assert_eq "$status_code" "1" "gen_ipv4 should fail on non-numeric input"
  expect_contains "$err" "Invalid characters in IPv4 address"
}
