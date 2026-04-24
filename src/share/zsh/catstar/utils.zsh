# Catstar General Utilities
# -----------------------------------------------------------------------------
# This file provides lightweight shell utilities, random string generators,
# and system inspection tools.
# -----------------------------------------------------------------------------

# --- Random String & Data Generation ---
# These functions use autoloaded 'randstr', 'gen_ipv4', and 'gen_ipv6' functions.

rs() { randstr "0-9a-z" "$@" }             # lowercase alphanumeric
rS() { randstr "0-9A-Z" "$@" }             # uppercase alphanumeric
rn() { randstr "0-9" "$@" }                # numeric only
rc() { randstr "0-9a-zA-Z" "$@" }          # mixed-case alphanumeric
rC() { randstr "a-zA-Z" "$@" }             # alphabetic only
rl() { randstr "a-z" "$@" }                # lowercase alphabetic
rL() { randstr "A-Z" "$@" }                # uppercase alphabetic
rh() { randstr "0-9a-f" "$@" }             # lowercase hex
rH() { randstr "0-9A-F" "$@" }             # uppercase hex
rp() { randstr '0-9A-Za-z!@#$%^&*()-+=' "$@" } # alphanumeric + symbols

r4() { gen_ipv4 "$@" }                     # random IPv4 address
r6() { gen_ipv6 "$@" }                     # random IPv6 address

# --- Visual & System Inspection ---

# colors: Display a 256-color chart in the terminal for testing color support.
colors() {
  local i
  for i in {0..255}; do
    printf "\x1b[38;5;${i}mcolor%-5i\x1b[0m" $i
    # Newline every 8 colors for a clean grid
    if ! (( ($i + 1 ) % 8 )); then
      print
    fi
  done
}


