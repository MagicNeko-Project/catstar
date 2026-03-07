# Archive wrappers and autoload stubs

tarc19() { tarc "$1" 19 "${@:2}" }
tarc22() { tarc "$1" 22 "${@:2}" }

7zc() {
  if (( $# == 0 )); then
    print "Usage: 7zc <directory_or_file> [7z_options...]"
    return 1
  fi
  local input=$1 output="${1}.7z"
  if [[ -e $output ]]; then
    print -u2 "Error: The file '$output' already exists."
    return 1
  fi
  shift
  7z a -t7z "$@" "$output" "$input"
}

7zc0() { 7zc "$@" -mtr- -mtm- }
7z0() { 7zc "$@" -mx0 }
7z5() { 7zc "$@" -mx5 }
7z9() { 7zc "$@" -mx9 }

zip0all() {
    local dir
    for dir in */(N); do
        local base_name=${dir:t}
        zip -0rj "${base_name}.zip" "$dir"
    done
}

mksquashfss0() {
    local fn=$1 dst=${2:-$1}
    if [[ -z $fn ]]; then return 1; fi
    if [[ -f "$dst.squashfs" ]]; then
        print -u2 "$dst.squashfs already exists."
        return 1
    fi
    sudo mksquashfs "$fn" "$dst.squashfs" -comp zstd -not-reproducible -root-owned -no-xattrs
}
