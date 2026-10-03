# Agent Guidelines

## 1. Operating Mandate
- **Full Autonomy:** Determine optimal implementation strategies autonomously, prioritizing readability and zero cognitive load.
- **Native Idioms:** Follow established community patterns rather than rigid, prescriptive rules.
- **Unbranded Code:** Ensure all generated code, UI strings, and documentation remain strictly unbranded. Omit project names, logos, or custom watermarks in favor of plain functional utility.
- **Domain Isolation:** The project is strictly partitioned into distinct areas. Confine file modifications to the active domain, except during global or project-level refactorings of a common theme.
- **Directory Maintenance:** Whenever a new conceptual or root-level directory is added to the project, update this file immediately to define its domain boundaries, ownership, and rules.

## 2. Domain Partitions
Each area operates under separate control and independent tooling:

- **`ansible/` (Server Provisioning):**
  - Infrastructure automation and server provisioning (YAML/Jinja2).
  - Enforce thin, modular roles, task idempotency, and `ansible-lint` compliance.

- **`app/` (Compiled Tools):**
  - Standalone structured, compiled tools (Go), kept strictly separate from the script directory.
  - Ownership includes root container packaging (`Dockerfile`, `.dockerignore`).
  - Internal tests are co-located within each tool directory under `app/`.

- **`scripts/` & `src/bin/` (Automation & CLI Tools):**
  - Standalone automation utilities, maintenance scripts, and CLI binaries (Python, Node.js, Shell).
  - Ownership includes root toolchain manifests (`pyproject.toml`, `package.json`, `biome.json`, `uv.lock`, `pnpm-lock.yaml`).
  - Associated test suites are located in `tests/python/` and `tests/node/`.
  - For `src/bin/`, only create symlinks when explicitly instructed by the user.

- **`src/share/zsh/` (Zsh Shell Environment):**
  - Modular Zsh configuration, prompt definitions, and autoloaded functions.
  - Pure native Zsh runtime; verified by the shell test suite in `tests/zsh/`.

- **`src/` & `stow.sh` (System Filesystem Overlay):**
  - Host filesystem mirror (`src/etc/`, `src/lib/systemd/`) deployed via the root `stow.sh` wrapper using GNU Stow.
  - Manages systemd unit definitions, configuration templates, and symlink deployment rules.
  - Excludes `src/bin/` (CLI Tools) and `src/share/zsh/` (Zsh Shell Environment).

- **`tests/` (Test Suites):**
  - Test suites partitioned strictly by domain (`tests/python/` and `tests/node/` for `scripts/`, `tests/zsh/` for `src/share/zsh/`).
  - Shared test harness infrastructure resides in `tests/lib/` and `tests/run_tests.zsh`.
  - Never treat `tests/` as a monolithic shared area; test edits must remain confined to the active domain's test suite.

- **`.github/` (CI/CD Workflows):**
  - Centralized GitHub Actions workflow definitions.
  - Workflows mirror domain toolchains and are modified strictly when updating automation for that domain.

## 3. Boundary Constraints
- **`config/` & `docs/`:** Static configuration and documentation with no relationship to the rest of the project. Do not inspect unless explicitly instructed by the user for specific named files.
- **`keys/`:** Do not inspect its content under any condition.
- **Untracked Files:** Strictly respect `.gitignore`. Never inspect, modify, or commit files not tracked by git.
