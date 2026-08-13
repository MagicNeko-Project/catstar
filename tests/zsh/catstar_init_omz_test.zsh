# Unit Tests for catstar_init_omz Core Function (Named Flags)
# -----------------------------------------------------------------------------

describe "CatstarInitOmzTest"

test_catstar_init_omz_skips_when_disabled() {
  catstar_init_omz --path "/non_existent_omz_path_123"
  assert_status 0 "catstar_init_omz must exit 0 immediately when --load flag is absent"
}

test_catstar_init_omz_fails_when_git_missing() {
  (
    PATH="/empty_test_path"
    catstar_init_omz --load --clone --path "/non_existent_omz_path_123"
  ) >/dev/null 2>&1
  assert_status 1 "catstar_init_omz must fail fast when git is missing and --clone is specified"
}
