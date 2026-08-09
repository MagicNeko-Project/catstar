# Unit Tests for Plugin-Based Zsh Loader System
# -----------------------------------------------------------------------------

describe "LoaderTest"

test_loader_fail_fast_on_missing_loader() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local output status_code

  output=$( (source "$catstar_script" --loader non_existent_loader_xyz) 2>&1 )
  status_code=$?

  assert_ne "$status_code" "0" "Missing loader must cause catstar.zsh to fail fast with non-zero status"
  expect_contains "$output" "Catstar Loader Error: Loader 'non_existent_loader_xyz' not found"
}

test_loader_fail_fast_in_bulk_loaders_list() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local output status_code

  output=$( (source "$catstar_script" --loaders "brew,invalid_loader_abc,pyenv") 2>&1 )
  status_code=$?

  assert_ne "$status_code" "0" "Invalid loader in bulk list must cause catstar.zsh to fail fast"
  expect_contains "$output" "Catstar Loader Error: Loader 'invalid_loader_abc' not found"
}

test_loader_path_traversal_sanitization() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local output status_code

  output=$( (source "$catstar_script" --loader "../../../etc/passwd") 2>&1 )
  status_code=$?

  assert_ne "$status_code" "0" "Path traversal loader attempt must fail fast"
  expect_contains "$output" "Catstar Loader Error: Loader 'passwd' not found"
}

test_loader_single_valid_loader() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local status_code

  (source "$catstar_script" --loader brew) >/dev/null 2>&1
  status_code=$?

  assert_eq "$status_code" "0" "Valid loader 'brew' should initialize successfully"
}

test_loader_multiple_valid_loaders() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local status_code

  (source "$catstar_script" --loader brew --loader pyenv --loader nvm --loader nodenv --loader rbenv --loader jenv --loader fnm) >/dev/null 2>&1
  status_code=$?

  assert_eq "$status_code" "0" "Multiple valid --loader arguments should initialize successfully"
}

test_loader_comma_and_colon_separated_list() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local status_code

  (source "$catstar_script" --loaders "cargo:go,direnv:sdkman,phpenv:goenv:tfenv") >/dev/null 2>&1
  status_code=$?

  assert_eq "$status_code" "0" "Comma and colon separated loaders list should parse and initialize successfully"
}

test_loader_env_var_initialization() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local status_code

  (
    CATSTAR_LOADERS="brew,pyenv,fnm,rbenv"
    source "$catstar_script"
  ) >/dev/null 2>&1
  status_code=$?

  assert_eq "$status_code" "0" "CATSTAR_LOADERS environment variable should specify default loaders"
}

test_loader_list_loaders_output() {
  local catstar_script="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar.zsh"
  local output status_code

  output=$(source "$catstar_script" --list-loaders)
  status_code=$?

  assert_eq "$status_code" "0" "--list-loaders should exit with 0 status code"
  expect_contains "$output" "Available loaders in"
  expect_contains "$output" "brew"
  expect_contains "$output" "pyenv"
  expect_contains "$output" "nodenv"
  expect_contains "$output" "rbenv"
  expect_contains "$output" "jenv"
  expect_contains "$output" "fnm"
  expect_contains "$output" "phpenv"
  expect_contains "$output" "goenv"
  expect_contains "$output" "tfenv"
}

test_loader_silent_skip_for_missing_tools() {
  local loaders_dir="${CATSTAR_ROOT:-$PWD}/src/share/zsh/catstar/loaders"
  local output status_code

  output=$(
    (
      PATH="/bin:/usr/bin"
      PYENV_ROOT="/non_existent_pyenv_path_12345"
      NODENV_ROOT="/non_existent_nodenv_path_12345"
      RBENV_ROOT="/non_existent_rbenv_path_12345"
      JENV_ROOT="/non_existent_jenv_path_12345"
      source "$loaders_dir/pyenv.zsh"
      source "$loaders_dir/nodenv.zsh"
      source "$loaders_dir/rbenv.zsh"
      source "$loaders_dir/jenv.zsh"
      source "$loaders_dir/fnm.zsh"
    ) 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "Loaders must return 0 when underlying tools are not installed"
  expect_eq "$output" "" "Loaders must skip silently without producing error messages"
}
