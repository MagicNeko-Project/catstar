# Project Test Directory

This directory contains unit test suites and framework utilities for testing project components.

## Directory Structure

```text
tests/
├── README.md              <-- Top-level test documentation
├── run_tests.zsh          <-- CLI runner for ZSH test suites
├── bootstrap.zsh          <-- Project environment loader for ZSH tests
├── lib/                   <-- Framework internal libraries
│   └── ztest.zsh          <-- ZTEST core assertion engine
└── zsh/                   <-- ZSH unit test suites
    ├── README.md          <-- ZSH Test Authoring Specification
    ├── sanity_randstr_test.zsh
    └── sanity_gen_ipv4_test.zsh
```

## Running ZSH Unit Tests

```bash
# Run all ZSH unit tests
./tests/run_tests.zsh

# Run specific test matching a pattern
./tests/run_tests.zsh --filter="IPv4*"

# List discovered test cases
./tests/run_tests.zsh --list
```
