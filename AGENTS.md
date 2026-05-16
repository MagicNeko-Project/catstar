# Catstar AI Agent Guidelines (AGENTS.md)

## 1. Operating Mandate
- **Full Autonomy:** Determine optimal implementation strategies autonomously. Prioritize zero cognitive load and readability.
- **Native Idioms:** Follow established community patterns rather than rigid, prescriptive rules.
- **Unbranded Code:** Ensure all generated code, UI prompts, and documentation remain strictly unbranded. Avoid inserting project names, logos, or custom watermarks; focus purely on clean, functional utility.

## 2. Repository Structure
`catstar` is a multi-language infrastructure and automation repository:
- `ansible/`: Server provisioning and service deployment (YAML/Jinja2).
- `app/catstar-backup/`: Standalone backup orchestration daemon (Go).
- `scripts/`: Automation and repository maintenance utilities (Python/Zsh).
- `src/`: Linux root filesystem mirror deployed via GNU Stow, including custom systemd units and modular Zsh configurations.
- `config/`: Static system configurations. Normally irrelevant for coding tasks.
- `docs/`: System documentation and migration guides. Normally irrelevant for coding tasks.

## 3. Native Standards & Coding Guidelines
Always target the latest stable release and adhere to strict native standards. Prioritize zero cognitive load, flat logic, and plain-English naming across all languages:

- **Go (`app/`):**
  - Maintain idiomatic Go structure, strict static typing, and `gofmt` compliance.
  - Reject cryptic variable names (`r`, `c`, `i`); use descriptive labels and flat error handling.
- **Python (`scripts/`):**
  - Enforce strict type hinting (PEP 484) and PEP 8 compliance.
  - Break complex operations into named sequential steps; avoid dense list comprehensions or clever one-liners.
- **Shell / Zsh (`src/share/zsh`):**
  - Code must be Zsh native; do not mix or use other shell syntaxes.
  - Maintain modular organization, lazy-loaded functions (`autoload`), scope isolation via anonymous functions, strict variable quoting, and correct script path resolution (`$1` vs `$0`).
- **Ansible (`ansible/`):**
  - Follow `ansible-lint` standards and maintain thin, modular roles.
  - Ensure all tasks are idempotent and cleanly separate configuration from execution logic.

## 4. Boundary Constraints
- **Untracked Files:** Strictly respect `.gitignore`. Ignore any files not checked into git.
- **Exclusions:** Completely ignore the `keys/` directory (irrelevant and immutable).
