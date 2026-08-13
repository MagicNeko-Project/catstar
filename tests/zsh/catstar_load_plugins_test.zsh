# Unit Tests for catstar_load_plugins Core Function
# -----------------------------------------------------------------------------

describe "CatstarLoadPluginsTest"

test_catstar_load_plugins_single_loader() {
  local loaders_dir="$CATSTAR_ROOT/src/share/zsh/catstar/loaders"

  catstar_load_plugins --dir "$loaders_dir" --loader brew >/dev/null 2>&1
  assert_status 0 "catstar_load_plugins should return 0 for valid loader 'brew'"
}

test_catstar_load_plugins_list_mode() {
  local loaders_dir="$CATSTAR_ROOT/src/share/zsh/catstar/loaders"
  local output

  output=$(catstar_load_plugins --dir "$loaders_dir" --list)
  assert_status 0 "catstar_load_plugins --list should return 0"
  expect_contains "$output" "Available loaders in"
  expect_contains "$output" "brew"
  expect_contains "$output" "pyenv"
}

test_catstar_load_plugins_fail_fast_on_missing() {
  local loaders_dir="$CATSTAR_ROOT/src/share/zsh/catstar/loaders"

  (
    catstar_load_plugins --dir "$loaders_dir" --loader non_existent_plugin_xyz
  ) >/dev/null 2>&1
  assert_status 1 "catstar_load_plugins must fail fast when a loader is missing"
}
