# Catstar Archive Utilities
# -----------------------------------------------------------------------------
# This file provides wrappers for various archiving tools (tar, 7z, zip, etc.)
# with sane defaults and specialized presets.
# -----------------------------------------------------------------------------

# --- Tar Wrappers ---
# tar0: Create archive with root ownership
tar0() { tar --numeric-owner --owner=0 --group=0 "$@" }

# tarz: Create Zstandard compressed archive
tarz() { tar --zstd "$@" }

# tarz0: Create Zstandard compressed archive with root ownership
tarz0() { tar --zstd --numeric-owner --owner=0 --group=0 "$@" }

# tarc19/tarc22: Quick presets for high compression levels using the tarc function
tarc19() { tarc "$1" 19 "${@:2}" }
tarc22() { tarc "$1" 22 "${@:2}" }

# --- 7-Zip Wrappers ---
# 7zc: Base function for creating 7z archives with error checking
7zc() {
  if (( $# == 0 )); then
    print -u2 "Usage: 7zc <directory_or_file> [7z_options...]"
    return 1
  fi
  local input=$1 
  local output="${1}.7z"
  
  if [[ -e "$output" ]]; then
    print -u2 "Error: The file '$output' already exists."
    return 1
  fi
  shift
  7z a -t7z "$@" "$output" "$input"
}

# Specialized 7z presets
7zc0() { 7zc "$@" -mtr- -mtm- } # Minimal metadata
7z0()  { 7zc "$@" -mx0 }        # No compression (store only)
7z5()  { 7zc "$@" -mx5 }        # Normal compression
7z9()  { 7zc "$@" -mx9 }        # Ultra compression

# --- Zip Utilities ---
# zip0all: Zip all directories in the current folder individually without compression
zip0all() {
  local dir
  for dir in */(N); do
    local base_name=${dir:t}
    zip -0rj "${base_name}.zip" "$dir"
  done
}

# zip_directory: Zip a single directory without compression and junking paths
zip_directory() {
  local dir=$1
  if [[ -d "$dir" ]]; then
    local base_name=${dir:t}
    zip -0rj "${base_name}.zip" "$dir"
  else
    print -u2 "Warning: '$dir' is not a directory"
  fi
}

# --- SquashFS Utilities ---
# mksquashfss0: Create a root-owned SquashFS image with Zstandard compression
mksquashfss0() {
  local fn=$1 
  local dst=${2:-$1}
  
  if [[ -z "$fn" ]]; then 
    print -u2 "Usage: mksquashfss0 <source> [destination_name]"
    return 1 
  fi
  
  if [[ -f "$dst.squashfs" ]]; then
    print -u2 "Error: $dst.squashfs already exists."
    return 1
  fi
  
  sudo mksquashfs "$fn" "$dst.squashfs" -comp zstd -not-reproducible -root-owned -no-xattrs
}
