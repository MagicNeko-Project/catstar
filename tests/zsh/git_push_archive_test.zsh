# Unit and behavioral verification tests for git-push-archive
# -----------------------------------------------------------------------------

describe "GitPushArchiveTest"

typeset -g TEST_WORKSPACE_DIR=""

SetUp() {
  TEST_WORKSPACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/git_push_archive_test_XXXXXX")"
}

TearDown() {
  if [[ -n "$TEST_WORKSPACE_DIR" && -d "$TEST_WORKSPACE_DIR" ]]; then
    rm -rf "$TEST_WORKSPACE_DIR"
  fi
}

_create_test_git_repo() {
  local target_directory="$1"
  local remote_origin_url="${2:-}"

  mkdir -p "$target_directory"
  command git -C "$target_directory" init -b main >/dev/null 2>&1
  command git -C "$target_directory" config user.email "tester@example.com"
  command git -C "$target_directory" config user.name "Synthetic Test User"
  command git -C "$target_directory" config commit.gpgsign false

  echo "init" > "$target_directory/README.txt"
  command git -C "$target_directory" add README.txt
  command git -C "$target_directory" commit -m "Synthetic initial commit" >/dev/null 2>&1

  if [[ -n "$remote_origin_url" ]]; then
    command git -C "$target_directory" remote add origin "$remote_origin_url"
  fi
}

test_git_push_archive_help_menu() {
  local output status_code
  output=$(git-push-archive --help)
  status_code=$?

  assert_eq "$status_code" "0" "git-push-archive --help should return 0"
  expect_contains "$output" "Usage: git-push-archive"
  expect_contains "$output" "--all"
}

test_git_push_archive_zero_args_shows_help() {
  local output status_code
  output=$(git-push-archive)
  status_code=$?

  assert_eq "$status_code" "0" "git-push-archive zero args should exit with 0"
  expect_contains "$output" "Usage: git-push-archive"
}

test_git_push_archive_outside_git_repository() {
  local err status_code
  err=$(
    cd "$TEST_WORKSPACE_DIR" && git-push-archive backup main 2>&1
  )
  status_code=$?

  expect_ne "$status_code" "0" "Should fail when run outside a git repository"
  expect_contains "$err" "Not inside a valid git repository"
}

test_git_push_archive_missing_remote_argument() {
  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/acme/project-alpha.git"

  local err status_code
  err=$(
    cd "$repo_dir" && git-push-archive --dry-run 2>&1
  )
  status_code=$?

  expect_ne "$status_code" "0" "Should fail when remote is missing"
  expect_contains "$err" "Destination remote required"
}

test_git_push_archive_mutex_all_and_branches() {
  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/acme/project-alpha.git"

  local err status_code
  err=$(
    cd "$repo_dir" && git-push-archive --all backup main 2>&1
  )
  status_code=$?

  expect_ne "$status_code" "0" "Should fail when combining --all with explicit branch"
  expect_contains "$err" "Cannot combine --all with branch arguments"
}

test_git_push_archive_single_branch() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/acme/project-alpha.git"
  command git -C "$repo_dir" remote add backup "$destination_remote"

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive backup main 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "git-push-archive <remote> <branch> should succeed"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_contains "$archived_refs" "refs/heads/acme/project-alpha/main"
}

test_git_push_archive_current_branch_default() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "git@example.com:core-team/service-backend.git"
  command git -C "$repo_dir" remote add backup "$destination_remote"
  command git -C "$repo_dir" checkout -b "feature/payment" >/dev/null 2>&1

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive backup 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "git-push-archive <remote> should push current branch"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_contains "$archived_refs" "refs/heads/core-team/service-backend/feature/payment"
}

test_git_push_archive_all_branches() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/acme/project-alpha.git"
  command git -C "$repo_dir" remote add backup "$destination_remote"

  command git -C "$repo_dir" branch "develop"
  command git -C "$repo_dir" branch "feature/ux"

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive --all backup 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "git-push-archive --all <remote> should succeed"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_contains "$archived_refs" "refs/heads/acme/project-alpha/main"
  expect_contains "$archived_refs" "refs/heads/acme/project-alpha/develop"
  expect_contains "$archived_refs" "refs/heads/acme/project-alpha/feature/ux"
}

test_git_push_archive_multiple_branches() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/acme/project-alpha.git"
  command git -C "$repo_dir" remote add backup "$destination_remote"

  command git -C "$repo_dir" branch "staging"
  command git -C "$repo_dir" branch "production"

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive backup staging production 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "Pushing multiple branches should succeed"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_contains "$archived_refs" "refs/heads/acme/project-alpha/staging"
  expect_contains "$archived_refs" "refs/heads/acme/project-alpha/production"
}

test_git_push_archive_cross_repo_collision_prevention() {
  local shared_vault="$TEST_WORKSPACE_DIR/central-vault.git"
  command git init --bare "$shared_vault" >/dev/null 2>&1

  local repo_one="$TEST_WORKSPACE_DIR/repo_one"
  local repo_two="$TEST_WORKSPACE_DIR/repo_two"

  _create_test_git_repo "$repo_one" "https://example.com/first-org/shared-tool.git"
  _create_test_git_repo "$repo_two" "https://example.com/second-org/shared-tool.git"

  command git -C "$repo_one" remote add central "$shared_vault"
  command git -C "$repo_two" remote add central "$shared_vault"

  ( cd "$repo_one" && git-push-archive central main ) >/dev/null 2>&1
  assert_eq "$?" "0" "Push from repo_one should succeed"

  ( cd "$repo_two" && git-push-archive central main ) >/dev/null 2>&1
  assert_eq "$?" "0" "Push from repo_two should succeed without conflict"

  local archived_refs
  archived_refs=$(command git -C "$shared_vault" show-ref)

  expect_contains "$archived_refs" "refs/heads/first-org/shared-tool/main"
  expect_contains "$archived_refs" "refs/heads/second-org/shared-tool/main"
}

test_git_push_archive_dry_run_flag() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/acme/dry-run-repo.git"
  command git -C "$repo_dir" remote add backup "$destination_remote"

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive -n backup main 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "Dry run push should exit cleanly"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_eq "$archived_refs" "" "Dry run must not create remote references"
}

test_git_push_archive_directory_fallback_without_origin() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/standalone_directory"
  _create_test_git_repo "$repo_dir" ""
  command git -C "$repo_dir" remote add backup "$destination_remote"

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive backup main 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "Should succeed using directory name fallback"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_contains "$archived_refs" "refs/heads/standalone_directory/main"
}

test_git_push_archive_prefix_override() {
  local destination_remote="$TEST_WORKSPACE_DIR/vault.git"
  command git init --bare "$destination_remote" >/dev/null 2>&1

  local repo_dir="$TEST_WORKSPACE_DIR/client_repo"
  _create_test_git_repo "$repo_dir" "https://example.com/default-org/default-repo.git"
  command git -C "$repo_dir" remote add backup "$destination_remote"

  local output status_code
  output=$(
    cd "$repo_dir" && git-push-archive --prefix "custom/override-namespace" backup main 2>&1
  )
  status_code=$?

  assert_eq "$status_code" "0" "git-push-archive --prefix should succeed"

  local archived_refs
  archived_refs=$(command git -C "$destination_remote" show-ref)
  expect_contains "$archived_refs" "refs/heads/custom/override-namespace/main"
}
