# Test file scanning and function auto-discovery for ztest.

ztest_discover_test_files() {
  setopt localoptions noksharrays
  local test_dir="$1"
  typeset -gaU DISCOVERED_FILES=()

  if (( ${#ZTEST_TARGET_FILES} > 0 )); then
    DISCOVERED_FILES=( "${(@)ZTEST_TARGET_FILES}" )
    return 0
  fi

  DISCOVERED_FILES=( "$test_dir"/**/*_test.zsh(N) "$test_dir"/*_test.zsh(N) )
}

ztest_discover_test_funcs() {
  setopt localoptions noksharrays

  typeset -gA TEST_FUNCS=()
  typeset -gA TEST_SUITES=()
  typeset -gA TEST_FILE_PATHS=()
  typeset -gaU DISCOVERED_TEST_KEYS=()

  local t_file="" fn_item=""
  for t_file in "${(@)DISCOVERED_FILES}"; do
    local -a old_tests=( ${(M)${(k)functions}:#test_*} ${(M)${(k)functions}:#test:*} )
    (( $+functions[SetUp] )) && old_tests+=( SetUp )
    (( $+functions[TearDown] )) && old_tests+=( TearDown )
    (( ${#old_tests} > 0 )) && unfunction "${(@)old_tests}"

    local -a funcs_before=() funcs_after=() new_funcs=()
    funcs_before=( ${(k)functions} )

    _ZTEST_CURRENT_SUITE="${t_file:t:r}"
    source "$t_file"

    funcs_after=( ${(k)functions} )
    new_funcs=( ${funcs_after:|funcs_before} )

    for fn_item in "${(@)new_funcs}"; do
      if [[ "$fn_item" == test_* || "$fn_item" == test:* ]]; then
        local s_name="$_ZTEST_CURRENT_SUITE"
        local t_name="$fn_item"

        if [[ "$fn_item" == test:* ]]; then
          local parts=( ${(s/:/)fn_item} )
          s_name="${parts[2]}"
          t_name="${parts[3]}"
        elif [[ "$fn_item" == test_* ]]; then
          t_name="${fn_item#test_}"
        fi

        local t_key="${s_name}.${t_name}"
        TEST_FUNCS[$t_key]="$fn_item"
        TEST_SUITES[$t_key]="$s_name"
        TEST_FILE_PATHS[$t_key]="$t_file"
        DISCOVERED_TEST_KEYS+=("$t_key")
      fi
    done
  done
}
