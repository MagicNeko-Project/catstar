# Catstar 

Catstar is a personal, multi-language repository for managing servers, automating daily tasks, and backing up data. It acts as the central hub for the configuration files, shell scripts, and compiled programs that keep the infrastructure running.

By keeping everything in one place, it's easier to track changes, share tools across different machines, and rebuild a server from scratch if something goes wrong.

## What's Inside

The repository is split into several main folders, each handling a different part of the system setup:

### `ansible/`
This folder holds the Ansible playbooks and roles used to set up servers automatically. Instead of running commands by hand, these scripts install packages, configure the firewall, and deploy services like Nginx, PHP, and v2ray. It ensures every server is set up exactly the same way.

### `config/` & `ssl/`
These directories store static configuration files that are deployed to the servers. 
*   **`config/nftables.conf`**: The main firewall ruleset.
*   **`ssl/`**: Contains the SSL/TLS certificate configurations and Diffie-Hellman parameters needed to secure web traffic.

### `keys/`
A secure storage area for public SSH keys (`id_ed25519.pub`) and Age encryption keys. These are used to grant access to servers or to encrypt and decrypt sensitive backup files.

### `scripts/`
A collection of Python and Bash tools for everyday tasks:
*   **`repo2txt.py`**: A Python script that scans a Git repository and converts its contents into a single, XML-formatted text file. This makes it easy to copy an entire codebase into an AI or LLM context window.
*   **`zipsync.py`**: A utility that copies a folder structure but automatically extracts any zip files it finds along the way.
*   **`clean_known_hosts.py`**: A small script to easily remove stale IP addresses from the SSH `known_hosts` file.

### `app/catstar-backup/`
A custom, standalone program written in Go that handles system backups. It reads a YAML configuration file to run multiple backup jobs at the same time. It can take BTRFS filesystem snapshots, upload data to remote servers using `restic`, or stream encrypted `tar` files over SSH. When a backup finishes (or fails), it automatically sends messages to Telegram and Discord, and pings a health-check website.

### `src/`
This folder mirrors a standard Linux filesystem (`/bin`, `/etc`, `/lib`). It contains the raw files that get copied directly onto a server, usually managed by a tool like GNU Stow.
*   **`src/lib/systemd/`**: Contains all the custom `systemd` service and timer files. These are what tell the server to run the backup program every night, auto-start Docker containers, or run maintenance tasks like `pacman` updates.
*   **`src/share/zsh/`**: Custom aliases, functions, and settings for the Zsh shell, making the command line easier to use.
