# Behavioral tests for completion directory registration in catstar.zsh
# -----------------------------------------------------------------------------

describe "CompletionFpathTest"

typeset -g TEST_WORKSPACE_DIR=""
typeset -g CATSTAR_LOADER_SCRIPT=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/completion_fpath_test_XXXXXX")"
  CATSTAR_LOADER_SCRIPT="$CATSTAR_ROOT/src/share/zsh/catstar.zsh"
}

TearDown() {
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

test_completion_directories_are_registered_before_omz_runs() {
  local xdg_data_dir="$TEST_WORKSPACE_DIR/xdg-data"
  local user_completions_dir="$xdg_data_dir/zsh/site-functions"
  local brew_prefix_dir="$TEST_WORKSPACE_DIR/homebrew"
  local brew_completions_dir="$brew_prefix_dir/share/zsh/site-functions"
  local stub_omz_dir="$TEST_WORKSPACE_DIR/omz"
  local recorded_fpath_file="$TEST_WORKSPACE_DIR/fpath_at_omz_init"

  mkdir -p "$user_completions_dir" "$brew_completions_dir" "$stub_omz_dir"
  print -r -- 'print -l -- "${fpath[@]}" > "'"$recorded_fpath_file"'"' > "$stub_omz_dir/oh-my-zsh.sh"

  (
    XDG_DATA_HOME="$xdg_data_dir"
    HOMEBREW_PREFIX="$brew_prefix_dir"
    source "$CATSTAR_LOADER_SCRIPT" --oh-my-zsh --oh-my-zsh-paths "$stub_omz_dir"
  )
  assert_status 0 "catstar.zsh must initialize cleanly with stub Oh My Zsh"

  local -a recorded_fpath
  recorded_fpath=("${(@f)$(<"$recorded_fpath_file")}")

  local catstar_functions_dir="$CATSTAR_ROOT/src/share/zsh/catstar/functions"
  local idx_catstar="${recorded_fpath[(Ie)$catstar_functions_dir]}"
  local idx_user="${recorded_fpath[(Ie)$user_completions_dir]}"
  local idx_brew="${recorded_fpath[(Ie)$brew_completions_dir]}"

  assert_ne "$idx_catstar" "0" "catstar/functions must be in fpath before oh-my-zsh runs"
  assert_ne "$idx_user" "0" "XDG user site-functions must be in fpath before oh-my-zsh runs"
  assert_ne "$idx_brew" "0" "Homebrew site-functions must be in fpath before oh-my-zsh runs"
  assert_eq "$(( idx_catstar < idx_user && idx_user < idx_brew ))" "1" \
    "Precedence must be catstar/functions > user site-functions > Homebrew site-functions"
}

test_completion_fpath_skips_missing_and_deduplicates_existing_entries() {
  local missing_xdg_dir="$TEST_WORKSPACE_DIR/does-not-exist"
  local brew_prefix_dir="$TEST_WORKSPACE_DIR/homebrew"
  local brew_completions_dir="$brew_prefix_dir/share/zsh/site-functions"
  local recorded_fpath_file="$TEST_WORKSPACE_DIR/fpath_after_source"

  mkdir -p "$brew_completions_dir"

  (
    fpath=("$brew_completions_dir" $fpath)
    XDG_DATA_HOME="$missing_xdg_dir"
    HOMEBREW_PREFIX="$brew_prefix_dir"
    source "$CATSTAR_LOADER_SCRIPT"
    print -l -- "${fpath[@]}" > "$recorded_fpath_file"
  )
  assert_status 0 "catstar.zsh must initialize cleanly when optional completion dirs are absent"

  local -a recorded_fpath
  recorded_fpath=("${(@f)$(<"$recorded_fpath_file")}")

  local missing_entry="$missing_xdg_dir/zsh/site-functions"
  expect_eq "${recorded_fpath[(Ie)$missing_entry]}" "0" "Non-existent completion directories must not be added to fpath"

  local match_count=0
  local entry
  for entry in "${recorded_fpath[@]}"; do
    [[ "$entry" == "$brew_completions_dir" ]] && (( match_count++ ))
  done
  expect_eq "$match_count" "1" "Duplicate completion directories must be deduplicated in fpath"
}

test_functions_directory_autoloads_files_and_symlinks_only() {
  local staged_root="$TEST_WORKSPACE_DIR/stowed"
  local target_dir="$TEST_WORKSPACE_DIR/targets"
  local result_file="$TEST_WORKSPACE_DIR/autoload_result"

  mkdir -p "$staged_root/catstar/functions/nested_dir" "$target_dir"
  ln -s "$CATSTAR_LOADER_SCRIPT" "$staged_root/catstar.zsh"
  print -r -- 'print -r -- "plain"' > "$staged_root/catstar/functions/plain_fn"
  print -r -- 'print -r -- "linked"' > "$target_dir/linked_fn"
  ln -s "$target_dir/linked_fn" "$staged_root/catstar/functions/linked_fn"
  ln -s "$target_dir/does_not_exist" "$staged_root/catstar/functions/broken_link"
  print -r -- '#compdef plain_fn' > "$staged_root/catstar/functions/_plain_fn"

  (
    source "$staged_root/catstar.zsh" >"$TEST_WORKSPACE_DIR/stdout" 2>&1
    print -r -- "plain=$+functions[plain_fn] linked=$+functions[linked_fn] broken=$+functions[broken_link] comp=$+functions[_plain_fn] dir=$+functions[nested_dir]" > "$result_file"
  )
  assert_status 0 "catstar.zsh must autoload functions cleanly from a stowed layout"
  expect_eq "$(<"$TEST_WORKSPACE_DIR/stdout")" "" "Function autoloading must not emit stdout"
  expect_eq "$(<"$result_file")" "plain=1 linked=1 broken=0 comp=0 dir=0" \
    "Autoloading must include regular files and valid symlinks while skipping _*, directories, and broken symlinks"
}
