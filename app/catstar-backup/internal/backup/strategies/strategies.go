package strategies

import (
	"context"
	"fmt"
	"log/slog"
	"os/exec"
	"strings"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

// CommandExecutor defines an interface for executing shell commands.
// Abstracting this allows us to mock system commands (like btrfs, tar, restic)
// during unit tests without modifying the host filesystem.
type CommandExecutor interface {
	Execute(ctx context.Context, cmdStr string, args ...string) ([]byte, error)
}

// DefaultCommandExecutor is the production implementation using os/exec.
type DefaultCommandExecutor struct {
	logger *slog.Logger
}

func NewDefaultCommandExecutor(logger *slog.Logger) *DefaultCommandExecutor {
	return &DefaultCommandExecutor{logger: logger}
}

func (d *DefaultCommandExecutor) Execute(ctx context.Context, cmdStr string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, cmdStr, args...)
	
	output, err := cmd.CombinedOutput()
	if err != nil {
		d.logger.Error("Command failed", 
			"command", cmdStr,
			"args", args,
			"error", err,
			"output", string(output),
		)
		return output, fmt.Errorf("command %s failed: %w", cmdStr, err)
	}

	d.logger.Debug("Command succeeded",
		"command", cmdStr,
		"output", string(output),
	)
	return output, nil
}

// ----------------------------------------------------------------------------
// Test Engine
// ----------------------------------------------------------------------------
type TestEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
}

func NewTestEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier) *TestEngine {
	return &TestEngine{cfg: cfg, logger: logger, notifier: notifier}
}

func (e *TestEngine) Name() string { return "test" }

func (e *TestEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Test Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：测试，只输出消息", e.cfg.MachineName))
	}

	for i := 1; i <= 2; i++ {
		e.logger.Info(fmt.Sprintf("测试备份消息：123*%d", i))
	}
	
	return nil
}

// ----------------------------------------------------------------------------
// Restic Engine
// ----------------------------------------------------------------------------
type ResticEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	executor CommandExecutor
}

func NewResticEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, executor CommandExecutor) *ResticEngine {
	return &ResticEngine{cfg: cfg, logger: logger, notifier: notifier, executor: executor}
}

func (e *ResticEngine) Name() string { return "restic_root" }

func (e *ResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Restic Root Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：restic", e.cfg.MachineName))
	}

	// Example: restic version
	if _, err := e.executor.Execute(ctx, "restic", "version"); err != nil {
		return err
	}

	// Execute restic backup
	args := []string{"backup", "--exclude-caches", "--one-file-system", e.cfg.ResticRoot}
	_, err := e.executor.Execute(ctx, "restic", args...)
	return err
}

// ----------------------------------------------------------------------------
// Tar SSH Engine
// ----------------------------------------------------------------------------
type TarSSHEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	executor CommandExecutor
}

func NewTarSSHEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, executor CommandExecutor) *TarSSHEngine {
	return &TarSSHEngine{cfg: cfg, logger: logger, notifier: notifier, executor: executor}
}

func (e *TarSSHEngine) Name() string { return "tar_ssh" }

func (e *TarSSHEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Tar SSH Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：tar.zst", e.cfg.MachineName))
	}

	// Simple mock of the bash date format replacement
	fileName := strings.ReplaceAll(e.cfg.TarFileName, "%(%F_%H%M%S)T", time.Now().Format("2006-01-02_150405"))

	pipeline := fmt.Sprintf("tar -I zstd -cp --one-file-system / | openssl %s -salt -k '%s' | dd bs=64K | ssh '%s' \"cat > '%s'\"",
		e.cfg.TarOpenSSLType,
		e.cfg.TarOpenSSLPassword,
		e.cfg.TarSSHServer,
		fileName,
	)

	e.logger.Debug("Executing shell pipeline", "pipeline", pipeline)
	
	_, err := e.executor.Execute(ctx, "bash", "-c", pipeline)
	if err != nil {
		return fmt.Errorf("tar SSH pipeline failed: %w", err)
	}

	return nil
}

// ----------------------------------------------------------------------------
// BTRFS Restic Engine
// ----------------------------------------------------------------------------
type BtrfsResticEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	executor CommandExecutor
}

func NewBtrfsResticEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, executor CommandExecutor) *BtrfsResticEngine {
	return &BtrfsResticEngine{cfg: cfg, logger: logger, notifier: notifier, executor: executor}
}

func (e *BtrfsResticEngine) Name() string { return "btrfs_restic" }

func (e *BtrfsResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing BTRFS Restic Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：btrfs 子卷快照 + restic", e.cfg.MachineName))
	}

	// 1. Delete old snapshots
	deleteCmd := fmt.Sprintf("btrfs subvolume delete %s/* || true", e.cfg.BtrfsSnapshotsRoot)
	_, _ = e.executor.Execute(ctx, "bash", "-c", deleteCmd) // Ignore errors on delete

	// 2. Create new snapshots
	for dest, src := range e.cfg.BtrfsSnapshots {
		destPath := fmt.Sprintf("%s/%s", e.cfg.BtrfsSnapshotsRoot, dest)
		if _, err := e.executor.Execute(ctx, "btrfs", "subvolume", "snapshot", "-r", src, destPath); err != nil {
			e.logger.Error("Failed to create btrfs snapshot", "src", src, "dest", destPath, "error", err)
			return err
		}
	}

	// 3. Run restic
	if _, err := e.executor.Execute(ctx, "restic", "version"); err != nil {
		return err
	}

	if _, err := e.executor.Execute(ctx, "restic", "backup", "--exclude-caches", e.cfg.BtrfsSnapshotsRoot); err != nil {
		e.logger.Error("Restic backup of btrfs snapshots failed", "error", err)
		// Try to clean up even if backup failed
		_, _ = e.executor.Execute(ctx, "bash", "-c", deleteCmd)
		return err
	}

	// 4. Clean up snapshots
	_, _ = e.executor.Execute(ctx, "bash", "-c", deleteCmd)

	return nil
}
