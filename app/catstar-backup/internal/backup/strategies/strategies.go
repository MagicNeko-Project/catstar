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

// Helper to log stdout/stderr of a command
func runCommand(ctx context.Context, logger *slog.Logger, cmdStr string, args ...string) error {
	cmd := exec.CommandContext(ctx, cmdStr, args...)
	
	// Capture output for logging (could be refined to stream line-by-line)
	output, err := cmd.CombinedOutput()
	if err != nil {
		logger.Error("Command failed", 
			"command", cmdStr,
			"args", args,
			"error", err,
			"output", string(output),
		)
		return fmt.Errorf("command %s failed: %w", cmdStr, err)
	}

	logger.Debug("Command succeeded",
		"command", cmdStr,
		"output", string(output),
	)
	return nil
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
	
	// Mimic the original script's exit code for testing if BACKUP_TEST is set to an int
	// For simplicity in this refactor, we just return nil. The main entry point 
	// should handle triggering a fake failure if needed.
	return nil
}

// ----------------------------------------------------------------------------
// Restic Engine
// ----------------------------------------------------------------------------
type ResticEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
}

func NewResticEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier) *ResticEngine {
	return &ResticEngine{cfg: cfg, logger: logger, notifier: notifier}
}

func (e *ResticEngine) Name() string { return "restic_root" }

func (e *ResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Restic Root Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：restic", e.cfg.MachineName))
	}

	// Example: restic version
	if err := runCommand(ctx, e.logger, "restic", "version"); err != nil {
		return err
	}

	// Execute restic backup
	args := []string{"backup", "--exclude-caches", "--one-file-system", e.cfg.ResticRoot}
	return runCommand(ctx, e.logger, "restic", args...)
}

// ----------------------------------------------------------------------------
// Tar SSH Engine
// ----------------------------------------------------------------------------
type TarSSHEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
}

func NewTarSSHEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier) *TarSSHEngine {
	return &TarSSHEngine{cfg: cfg, logger: logger, notifier: notifier}
}

func (e *TarSSHEngine) Name() string { return "tar_ssh" }

func (e *TarSSHEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Tar SSH Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：tar.zst", e.cfg.MachineName))
	}

	// This is a complex pipeline: tar | openssl | dd | ssh
	// In Go, executing a shell pipeline directly is often easiest via bash -c
	// Note: We use the format string from the bash script. In a real scenario,
	// you'd want to parse '%(%F_%H%M%S)T' properly or just use Go's time formatting.
	
	// Simple mock of the bash date format replacement
	fileName := strings.ReplaceAll(e.cfg.TarFileName, "%(%F_%H%M%S)T", time.Now().Format("2006-01-02_150405"))

	pipeline := fmt.Sprintf("tar -I zstd -cp --one-file-system / | openssl %s -salt -k '%s' | dd bs=64K | ssh '%s' \"cat > '%s'\"",
		e.cfg.TarOpenSSLType,
		e.cfg.TarOpenSSLPassword,
		e.cfg.TarSSHServer,
		fileName,
	)

	e.logger.Debug("Executing shell pipeline", "pipeline", pipeline)
	
	cmd := exec.CommandContext(ctx, "bash", "-c", pipeline)
	
	output, err := cmd.CombinedOutput()
	if err != nil {
		e.logger.Error("Tar SSH Pipeline failed", 
			"error", err,
			"output", string(output),
		)
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
}

func NewBtrfsResticEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier) *BtrfsResticEngine {
	return &BtrfsResticEngine{cfg: cfg, logger: logger, notifier: notifier}
}

func (e *BtrfsResticEngine) Name() string { return "btrfs_restic" }

func (e *BtrfsResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing BTRFS Restic Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：btrfs 子卷快照 + restic", e.cfg.MachineName))
	}

	// 1. Delete old snapshots
	deleteCmd := fmt.Sprintf("btrfs subvolume delete %s/* || true", e.cfg.BtrfsSnapshotsRoot)
	_ = runCommand(ctx, e.logger, "bash", "-c", deleteCmd) // Ignore errors on delete

	// 2. Create new snapshots
	for dest, src := range e.cfg.BtrfsSnapshots {
		destPath := fmt.Sprintf("%s/%s", e.cfg.BtrfsSnapshotsRoot, dest)
		if err := runCommand(ctx, e.logger, "btrfs", "subvolume", "snapshot", "-r", src, destPath); err != nil {
			e.logger.Error("Failed to create btrfs snapshot", "src", src, "dest", destPath, "error", err)
			return err
		}
	}

	// 3. Run restic
	if err := runCommand(ctx, e.logger, "restic", "version"); err != nil {
		return err
	}

	if err := runCommand(ctx, e.logger, "restic", "backup", "--exclude-caches", e.cfg.BtrfsSnapshotsRoot); err != nil {
		e.logger.Error("Restic backup of btrfs snapshots failed", "error", err)
		// Try to clean up even if backup failed
		_ = runCommand(ctx, e.logger, "bash", "-c", deleteCmd)
		return err
	}

	// 4. Clean up snapshots
	_ = runCommand(ctx, e.logger, "bash", "-c", deleteCmd)

	return nil
}
