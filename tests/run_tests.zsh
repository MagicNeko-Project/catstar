#!/usr/bin/env zsh
# Test runner entry point launcher.

() {
  setopt localoptions noksharrays

  local script_path="${(%):-%x}"
  local test_dir="${script_path:a:h}"
  local lib_dir="${ZTEST_LIB_DIR:-${test_dir}/lib}"

  local engine_script=""
  if [[ -f "${lib_dir}/ztest.zsh" ]]; then
    engine_script="${lib_dir}/ztest.zsh"
  elif [[ -f "${test_dir}/ztest.zsh" ]]; then
    engine_script="${test_dir}/ztest.zsh"
  fi

  if [[ -z "$engine_script" ]]; then
    print -u2 "Error: ztest framework engine not found in ${lib_dir} or ${test_dir}"
    return 1
  fi

  source "$engine_script"
  ztest_main "$test_dir" "$@"
} "$@"
