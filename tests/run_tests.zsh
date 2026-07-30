#!/usr/bin/env zsh
# Test runner entry point launcher.

() {
  setopt localoptions noksharrays

  local script_path="${(%):-%x}"
  local test_dir="${script_path:a:h}"
  local lib_dir="${test_dir}/lib"

  if [[ ! -f "${lib_dir}/ztest.zsh" ]]; then
    print -u2 "Error: ztest framework library not found in ${lib_dir}"
    return 1
  fi

  source "${lib_dir}/ztest.zsh"
  ztest_main "$test_dir" "$@"
} "$@"
