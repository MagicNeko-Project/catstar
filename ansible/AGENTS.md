# Server Provisioning Guidelines

## Provisioning Architecture
- **Three-Layer Model:**
  1. *Generic Units (`../src/lib/systemd/system/`):* System services and Podman containers are authored as generic, reusable systemd units deployed to `/usr/local/lib/systemd/system/` via GNU Stow (`stow.sh`). Units define defaults and load host-specific environment overrides via `EnvironmentFile=-/usr/local/etc/<unit>.conf`.
  2. *Stateless Roles (`play.yml`):* Playbook roles (`local.infra.common`, `ssl`, `nginx`, `v2ray`) provide generic mechanisms. Adding or migrating a host service rarely modifies role code.
  3. *Host Inventories:* Host configuration files define per-host parameters, including `/usr/local/etc/*.conf` environment files via `common_create_configs`, and reverse-proxy routing via `nginx_upstreams` / `nginx_sites_enabled`.

## Dynamic Discovery & Decoupling
- **Autonomous Discovery:** Dynamically explore file locations rather than hardcoding paths:
  - *Inventories:* Auto-discover inventory directories (e.g. `hosts/`, `/etc/ansible/hosts/`, or companion worktrees).
  - *Certificates:* Auto-discover certificate stores (e.g. `certs/`, `~/.acme.sh/certs/`) rather than assuming fixed locations.
  - *Role Defaults:* Inspect `collections/ansible_collections/local/infra/roles/<role>/defaults/main.yml` to verify variable names and defaults.
- **Repository Isolation:** Host inventories and certificate stores are independent Git repositories with distinct version histories. Never leak host-specific inventory details into commits made in this repository.

