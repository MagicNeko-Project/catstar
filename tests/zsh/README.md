# Test Authoring Specification

This document defines the behavioral contracts, API specifications, and authoring guidelines for writing unit tests using `ztest`.

---

## 1. Core Principles

- **Native ZSH Ergonomics**: Tests are written as standard, executable ZSH functions (`test_*`). Editors provide syntax highlighting, auto-completion, static linting, and auto-formatting out-of-the-box.
- **Hermetic Test Isolation**: Every test case runs in an isolated subshell environment. State changes made inside a test case (environment variables, `setopt` flags, working directory, traps) do not persist beyond that test case.
- **Dual Assertion Model**:
  - **Soft Expectations (`expect_*`)**: Non-fatal checks. Logs failure details and continues execution so all failures in a single test case can be observed.
  - **Hard Assertions (`assert_*`)**: Fatal checks. Logs failure details and immediately halts execution of the current test case.
- **Standalone Protocol**: Test suites are portable and can run in any ZSH project environment.

---

## 2. Test Suite & Test Case Structure

### 2.1 Suite Scope (`describe`)
Use `describe "Suite Name"` at the top of a test file to set the test suite scope:

```zsh
describe "StringUtilitiesTest"
```

### 2.2 Test Case Definition
Define test cases as standard ZSH functions prefixed with `test_`. The runner automatically discovers defined test functions:

```zsh
describe "StringUtilitiesTest"

test_concatenates_two_strings() {
  local result=$(concat "hello" "world")
  expect_eq "$result" "helloworld"
}

test_trims_whitespace() {
  local result=$(trim "  hello  ")
  expect_eq "$result" "hello"
}
```

#### Explicit Naming Syntax
For self-contained test functions where the suite name is embedded in the function identifier, use colon-delimited syntax `test:<SuiteName>:<TestCaseName>`:

```zsh
test:StringUtilitiesTest:TrimsWhitespace() {
  local result=$(trim "  hello  ")
  expect_eq "$result" "hello"
}
```

---

## 3. Assertion & Expectation API Specification

All assertion and expectation functions accept an optional trailing argument `[message]` to provide custom diagnostic context on failure.

### 3.1 Equality & Inequality

#### `expect_eq <actual> <expected> [message]` / `assert_eq <actual> <expected> [message]`
Asserts that `<actual>` and `<expected>` are string-identical.

```zsh
expect_eq "$actual_val" "expected_val" "Value should match exact string"
assert_eq "$return_code" "0" "Command must complete successfully"
```

#### `expect_ne <val1> <val2> [message]` / `assert_ne <val1> <val2> [message]`
Asserts that `<val1>` and `<val2>` are NOT identical.

```zsh
expect_ne "$new_token" "$old_token" "Generated tokens must be unique"
```

---

### 3.2 Pattern & Substring Matching

#### `expect_match <pattern> <value> [message]` / `assert_match <pattern> <value> [message]`
Asserts that `<value>` matches the ZSH regular expression pattern `<pattern>` (evaluates with standard ZSH `=~` regex semantics).

```zsh
expect_match "^[0-9]{3}-[0-9]{4}$" "$phone_number" "Must match phone format"
assert_match "^https://" "$url" "URL must use secure HTTPS protocol"
```

#### `expect_contains <string> <substring> [message]` / `assert_contains <string> <substring> [message]`
Asserts that `<string>` contains `<substring>` anywhere within its content.

```zsh
expect_contains "$error_log" "Permission denied"
assert_contains "$output" "SUCCESS"
```

---

### 3.3 Status & Exit Code Inspection

#### `expect_status <expected_code> [message]` / `assert_status <expected_code> [message]`
Asserts that the exit status (`$?` / `$status`) of the **immediately preceding statement or function call** equals `<expected_code>`.

> **Contract Rule:** `expect_status` / `assert_status` MUST be placed immediately after the function or command execution under test.

```zsh
# Test happy path status
gen_ipv4 "10.0.0.0/8"
expect_status 0 "Valid subnet mask should exit with status 0"

# Test error handling status
gen_ipv4 "invalid_input" 2>/dev/null
assert_status 1 "Invalid input must yield exit status 1"
```

---

## 4. Test Fixtures & Lifecycle Hooks

Test files can define optional lifecycle hooks to manage environment setup and teardown around every test case.

### 4.1 `SetUp()`
If `SetUp()` is defined in a test file, it is invoked **immediately before** running each test case.

**Contract:** If `SetUp()` returns a non-zero exit status, the test case is aborted immediately and marked as a failure without executing the test function.

```zsh
SetUp() {
  typeset -g TEST_TEMP_DIR=$(mktemp -d)
  cd "$TEST_TEMP_DIR" || return 1
}
```

### 4.2 `TearDown()`
If `TearDown()` is defined in a test file, it is invoked **immediately after** running each test case.

**Contract:** `TearDown()` runs regardless of whether the test case passed or failed, guaranteeing resources can be cleaned up reliably.

```zsh
TearDown() {
  if [[ -n "$TEST_TEMP_DIR" && -d "$TEST_TEMP_DIR" ]]; then
    rm -rf "$TEST_TEMP_DIR"
  fi
}
```

---

## 5. Authoring Best Practices

1. **Prefer Soft Expectations by Default**: Use `expect_*` instead of `assert_*` for general checks. Soft expectations allow test authors to see all failing checks in a single test run.
2. **Use Hard Assertions for Preconditions**: Use `assert_*` when a subsequent step in the test case depends strictly on the success of an earlier operation (e.g. verifying a file exists before opening it).
3. **Keep Tests Self-Contained**: Avoid relying on external network calls or persistent machine state. Mock external dependencies or use temporary paths.
4. **Cover Happy Paths and Error Paths**: Test valid inputs, boundary conditions, and invalid inputs.

---

## 6. Running Tests CLI Reference

Execute test suites using the CLI runner:

```bash
# Run all test suites
./tests/run_tests.zsh

# Run specific test suites or cases matching a pattern
./tests/run_tests.zsh --filter="IPv4GeneratorTest.*"
./tests/run_tests.zsh -f "*valid_input*"

# List discovered test suites and test cases without running
./tests/run_tests.zsh --list

# Stop test execution immediately on the first failed test
./tests/run_tests.zsh --break-on-failure

# Specify a custom bootstrap script for environment initialization
./tests/run_tests.zsh --bootstrap=path/to/bootstrap.zsh
```

---

## 7. API Summary Matrix

| Concept | Authoring Syntax | Behavior / Semantics |
| :--- | :--- | :--- |
| **Suite Declaration** | `describe "SuiteName"` | Groups test functions under a logical suite name |
| **Test Case** | `test_name() { ... }` | Standard ZSH function; executed in an isolated environment |
| **Soft Expectation** | `expect_eq`, `expect_match`, etc. | Logs failure details on mismatch; **continues execution** |
| **Hard Assertion** | `assert_eq`, `assert_match`, etc. | Logs failure details on mismatch; **aborts test immediately** |
| **Status Check** | `expect_status 0` | Inspects `$status` of the immediately preceding command |
| **Pre-Test Hook** | `SetUp()` | Runs before each test; aborts test if non-zero exit |
| **Post-Test Hook** | `TearDown()` | Runs after each test regardless of pass/fail status |
