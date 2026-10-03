# Project Test Suites

This directory houses domain-partitioned test suites for project components. Each subdirectory is fully autonomous with its own runtime tooling and execution harness.

## Directory Structure

```text
tests/
├── README.md              <-- Top-level test documentation
├── zsh/                   <-- Native Zsh test suites, CLI runner, and ztest framework
│   ├── run.zsh            <-- CLI runner for Zsh test suites
│   ├── bootstrap.zsh      <-- Environment loader for Zsh tests
│   ├── lib/               <-- ztest framework modules
│   └── README.md          <-- Zsh test authoring specification
├── python/                <-- Python unit test suites (unittest)
└── node/                  <-- Node.js unit test suites (node --test)
```

## Running Unit Tests

### Zsh Unit Tests

```bash
# Run all Zsh unit tests
./tests/zsh/run.zsh

# Run specific test matching a pattern
./tests/zsh/run.zsh --filter="IPv4*"

# List discovered test cases
./tests/zsh/run.zsh --list
```

### Python Unit Tests

```bash
# Run all Python unit tests
python3 -m unittest discover -s tests/python -p "test_*.py"
```

### Node.js Unit Tests

```bash
# Run all Node.js unit tests
node --test tests/node/*.test.js
```
