# Catstar Backup

Catstar Backup is a modernized, strongly-typed Go application designed to orchestrate system backups. It abstracts the execution of strategies like BTRFS snapshots, Restic uploads, and Tar streaming. 

This project evolved from a monolithic Bash script into a domain-driven Go project designed for reliability, concurrency, and observability.

## Architecture & Modules

The application is structured following clean architecture principles to maximize testability and separation of concerns.

* **`cmd/catstar-backup/`**: The main entry point. Bootstraps the application, parses configurations, wires dependencies, and triggers the orchestrator.
* **`internal/config/`**: Strictly parses and validates system environment variables. Instead of checking configurations during backup execution, it fails fast on startup.
* **`internal/backup/`**: Contains the core business logic. 
  * **`orchestrator.go`**: Manages the sequential/concurrent lifecycle of configured backup strategies and logs outputs.
  * **`strategies/`**: Implements the execution engines (e.g., `BtrfsResticEngine`, `TarSSHEngine`). Uses a `CommandExecutor` interface to decouple shell commands from the execution logic, enabling destructive tests to run safely via mocks.
* **`internal/notify/`**: Implements the Composite/Fan-Out pattern to dispatch notifications (Telegram, Discord, Debug) concurrently without blocking.
* **`internal/observability/`**: Manages logging buffers and telemetry HTTP pings, breaking the hard coupling to `systemd/journalctl`.

## Safe Unit Testing

To ensure safety when testing destructive backup strategies (like deleting BTRFS subvolumes), the application injects a `CommandExecutor` interface.

In production, the `DefaultCommandExecutor` runs actual `exec.CommandContext` system calls. In tests, the `MockCommandExecutor` merely records the CLI command that *would* have been run and returns a predetermined success/failure, preventing any actual modifications to the host filesystem.

To run the full suite securely:
```bash
cd app/catstar-backup
go test ./... -v
```

## Compilation

```bash
cd app/catstar-backup
go build -o bin/catstar-backup ./cmd/catstar-backup
```
