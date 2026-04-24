# General lightweight shell utilities and function stubs

# Heavy functions are autoloaded from catstar/functions/
# This file contains wrappers and small functions.

# Random string wrappers
rs() { randstr "0-9a-z" "$@" }
rS() { randstr "0-9A-Z" "$@" }
rn() { randstr "0-9" "$@" }
rc() { randstr "0-9a-zA-Z" "$@" }
rC() { randstr "a-zA-Z" "$@" }
rl() { randstr "a-z" "$@" }
rL() { randstr "A-Z" "$@" }
rh() { randstr "0-9a-f" "$@" }
rH() { randstr "0-9A-F" "$@" }
rp() { randstr '0-9A-Za-z!@#$%^&*()-+=' "$@" }
r4() { gen_ipv4 "$@" }
r6() { gen_ipv6 "$@" }

colors() {
    local i
    for i in {0..255}; do
        printf "\x1b[38;5;${i}mcolor%-5i\x1b[0m" $i
        if ! (( ($i + 1 ) % 8 )); then
            print
        fi
    done
}


