# catstar

Centralized repository for host provisioning, system automation, and backup orchestration, providing declarative configurations, root filesystem overlays, modular shell environments, and compiled infrastructure services.

## Repository Architecture

The repository is partitioned into isolated functional domains:

### `ansible/`
Ansible playbooks and roles used to provision and configure servers automatically. These playbooks install packages, configure firewall rules, and deploy services like Nginx, PHP, and v2ray, ensuring consistent server states.

### `app/`
Standalone structured, compiled tools (Go) with co-located internal tests, kept strictly separate from the script directory.

### `scripts/` & `src/bin/`
Standalone automation utilities, maintenance scripts, and CLI binaries (Python, Node.js, Shell).

### `src/share/zsh/`
Modular native Zsh shell environment and autoloaded functions, providing customized CLI settings, completion loaders, and prompt configurations.

### `src/` & `stow.sh`
Linux filesystem overlay mirroring host directories (`/etc`, `/lib/systemd`) managed via GNU Stow:
- **`src/lib/systemd/`**: Custom systemd service and timer unit definitions for background daemons, automated container management, and periodic maintenance tasks.
- **`src/etc/`**: Service-specific configuration templates and IP sets.
- **`stow.sh`**: Symlink deployment script that safely manages and folds links into the host system (e.g., `/usr/local`).

### `tests/`
Automated test suites partitioned by domain (Go tests are co-located within `app/`):
- **`tests/python/`**: Unit tests for Python automation scripts.
- **`tests/node/`**: Unit tests for Node.js utilities.
- **`tests/zsh/`**: Dedicated test harness and behavioral suites verifying modular Zsh functions and loaders.

### `.github/`
Continuous integration workflows automating testing, linting, and build verification across all repository domains.

### `config/` & `docs/`
Static configuration files and isolated operational documentation manuals with no relationship to runtime code.

### `keys/`
Sample demonstration keys for testing and syntax validation.
