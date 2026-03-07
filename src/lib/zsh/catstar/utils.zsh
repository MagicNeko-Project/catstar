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
r6() {
    local r=$(rh 32)
    print "fd${r:0:2}:${r:2:4}:${r:6:4}:${r:10:4}:${r:14:4}:${r:18:4}:${r:22:4}:${r:26:4}"
}

colors() {
    local i
    for i in {0..255}; do
        printf "\x1b[38;5;${i}mcolor%-5i\x1b[0m" $i
        if ! (( ($i + 1 ) % 8 )); then
            print
        fi
    done
}

zip_directory() {
    local dir=$1
    if [[ -d "$dir" ]]; then
        local base_name=${dir:t}
        zip -0rj "${base_name}.zip" "$dir"
    else
        print -u2 "Warning: '$dir' is not a directory"
    fi
}
