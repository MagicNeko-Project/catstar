# Unit and behavioral verification tests for git-profile
# -----------------------------------------------------------------------------

describe "GitProfileTest"

typeset -g TEST_WORKSPACE_DIR=""
typeset -g OLD_HOME=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/git_profile_test_XXXXXX")"
  mkdir -p "$TEST_WORKSPACE_DIR/home"
  OLD_HOME="$HOME"
  export HOME="$TEST_WORKSPACE_DIR/home"
}

TearDown() {
  export HOME="$OLD_HOME"
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

_create_test_repo() {
  local target_directory="$1"
  mkdir -p "$target_directory"
  command git -C "$target_directory" init -b main >/dev/null 2>&1
  command git -C "$target_directory" config user.email "dev@example.com"
  command git -C "$target_directory" config user.name "Dev User"
  command git -C "$target_directory" config commit.gpgsign false

  echo "content" > "$target_directory/file.txt"
  command git -C "$target_directory" add file.txt
  command git -C "$target_directory" commit -m "Initial commit" >/dev/null 2>&1
}

test_git_profile_help_menu() {
  local output status_code
  output=$(git-profile --help)
  status_code=$?

  assert_eq "$status_code" "0" "git-profile --help should return 0"
  expect_contains "$output" "Usage: git-profile"
  expect_contains "$output" "use [<name>]"
}

test_git_profile_current_empty() {
  local output status_code
  output=$(git-profile current --global)
  status_code=$?

  assert_eq "$status_code" "0" "git-profile current should return 0"
  expect_contains "$output" "(No Git identity is currently configured)"
}

test_git_profile_add_and_current() {
  local repo_dir="$TEST_WORKSPACE_DIR/repo"
  _create_test_repo "$repo_dir"

  local output status_code
  output=$(
    cd "$repo_dir" && git-profile add work HEAD --use
  )
  status_code=$?

  assert_eq "$status_code" "0" "git-profile add should succeed"
  expect_contains "$output" "Profile 'work' was successfully created."

  local current_out
  current_out=$(cd "$repo_dir" && git-profile current --local)
  expect_contains "$current_out" "Profile:  work"
  expect_contains "$current_out" "Identity: Dev User <dev@example.com>"
}

test_git_profile_use_and_clear() {
  local repo_dir="$TEST_WORKSPACE_DIR/repo"
  _create_test_repo "$repo_dir"

  # Add profile into global config
  command git config --global profile.personal.name "Alice Smith"
  command git config --global profile.personal.email "alice@example.com"

  local use_out status_code
  use_out=$(cd "$repo_dir" && git-profile use personal)
  status_code=$?

  assert_eq "$status_code" "0" "git-profile use personal should succeed"
  expect_contains "$use_out" "Git identity (--local) set to: Alice Smith <alice@example.com>"

  local name_local email_local
  name_local=$(command git -C "$repo_dir" config --local user.name)
  email_local=$(command git -C "$repo_dir" config --local user.email)
  assert_eq "$name_local" "Alice Smith" "Local user.name matches"
  assert_eq "$email_local" "alice@example.com" "Local user.email matches"

  # Clear local profile
  local clear_out
  clear_out=$(cd "$repo_dir" && git-profile clear)
  status_code=$?
  assert_eq "$status_code" "0" "git-profile clear should succeed"
  expect_contains "$clear_out" "Successfully cleared identity for profile 'personal'"
}

test_git_profile_set_rename_delete() {
  command git config --global profile.testprof.name "Test User"
  command git config --global profile.testprof.email "test@example.com"

  # Set key
  local set_out status_code
  set_out=$(git-profile set testprof email "updated@example.com")
  status_code=$?
  assert_eq "$status_code" "0" "git-profile set should succeed"
  expect_contains "$set_out" "Successfully updated profile 'testprof'"

  local new_email
  new_email=$(command git config --global profile.testprof.email)
  assert_eq "$new_email" "updated@example.com" "Updated email in config"

  # Rename
  local rename_out
  rename_out=$(git-profile rename testprof newprof)
  status_code=$?
  assert_eq "$status_code" "0" "git-profile rename should succeed"

  local renamed_name
  renamed_name=$(command git config --global profile.newprof.name)
  assert_eq "$renamed_name" "Test User" "Renamed profile name matches"

  # Delete
  local delete_out
  delete_out=$(git-profile delete newprof)
  status_code=$?
  assert_eq "$status_code" "0" "git-profile delete should succeed"

  local deleted_check
  deleted_check=$(command git config --global profile.newprof.name 2>/dev/null)
  assert_eq "$deleted_check" "" "Profile section was removed"
}

test_git_profile_export_and_import() {
  command git config --global profile.p1.name "User One"
  command git config --global profile.p1.email "one@example.com"
  command git config --global profile.p2.name "User Two"
  command git config --global profile.p2.email "two@example.com"

  local export_file="$TEST_WORKSPACE_DIR/exported.gitconfig"
  local export_out status_code
  export_out=$(git-profile export -o "$export_file")
  status_code=$?
  assert_eq "$status_code" "0" "git-profile export should succeed"

  # Delete profiles
  command git config --global --remove-section profile.p1
  command git config --global --remove-section profile.p2

  # Import profiles
  local import_out
  import_out=$(git-profile import "$export_file")
  status_code=$?
  assert_eq "$status_code" "0" "git-profile import should succeed"
  expect_contains "$import_out" "Successfully imported 2 profile(s)"

  local p1_name p2_name
  p1_name=$(command git config --global profile.p1.name)
  p2_name=$(command git config --global profile.p2.name)
  assert_eq "$p1_name" "User One" "Imported p1 matches"
  assert_eq "$p2_name" "User Two" "Imported p2 matches"

  # Import duplicate without --force should fail
  local err
  err=$(git-profile import "$export_file" 2>&1)
  status_code=$?
  expect_ne "$status_code" "0" "Importing duplicate without --force should fail"
  expect_contains "$err" "already exists. Use --force flag"

  # Import duplicate with --force should succeed
  import_out=$(git-profile import "$export_file" --force)
  status_code=$?
  assert_eq "$status_code" "0" "Importing duplicate with --force should succeed"
}

test_git_profile_use_commit_and_authors() {
  local repo_dir="$TEST_WORKSPACE_DIR/repo"
  _create_test_repo "$repo_dir"

  local use_commit_out status_code
  use_commit_out=$(cd "$repo_dir" && git-profile use-commit HEAD)
  status_code=$?
  assert_eq "$status_code" "0" "use-commit HEAD should succeed"
  expect_contains "$use_commit_out" "Git identity (--local) set to: Dev User <dev@example.com>"

  local authors_out
  authors_out=$(cd "$repo_dir" && git-profile authors)
  status_code=$?
  assert_eq "$status_code" "0" "authors should succeed"
  expect_contains "$authors_out" "Dev User <dev@example.com>"
}

test_git_profile_outside_repo_errors() {
  local err status_code
  err=$(cd "$TEST_WORKSPACE_DIR" && git-profile use work 2>&1)
  status_code=$?
  expect_ne "$status_code" "0" "git-profile use without --global outside repo should fail"
  expect_contains "$err" "Not inside a Git repository"
}
