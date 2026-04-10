package strategies

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

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
	factory  CommandFactory
}

func NewResticEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, factory CommandFactory) *ResticEngine {
	return &ResticEngine{cfg: cfg, logger: logger, notifier: notifier, factory: factory}
}

func (e *ResticEngine) Name() string { return "restic_root" }

func (e *ResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Restic Root Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：restic", e.cfg.MachineName))
	}

	if err := runSimpleCommand(ctx, e.factory, e.logger, "restic", "version"); err != nil {
		return err
	}

	return runSimpleCommand(ctx, e.factory, e.logger, "restic", "backup", "--exclude-caches", "--one-file-system", e.cfg.ResticRoot)
}

// ----------------------------------------------------------------------------
// BTRFS Restic Engine
// ----------------------------------------------------------------------------
type BtrfsResticEngine struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	factory  CommandFactory
}

func NewBtrfsResticEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, factory CommandFactory) *BtrfsResticEngine {
	return &BtrfsResticEngine{cfg: cfg, logger: logger, notifier: notifier, factory: factory}
}

func (e *BtrfsResticEngine) Name() string { return "btrfs_restic" }

func (e *BtrfsResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing BTRFS Restic Backup Engine")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：btrfs 子卷快照 + restic", e.cfg.MachineName))
	}

	deleteCmd := fmt.Sprintf("btrfs subvolume delete %s/* || true", e.cfg.BtrfsSnapshotsRoot)
	_ = runSimpleCommand(ctx, e.factory, e.logger, "bash", "-c", deleteCmd) 

	for dest, src := range e.cfg.BtrfsSnapshots {
		destPath := fmt.Sprintf("%s/%s", e.cfg.BtrfsSnapshotsRoot, dest)
		if err := runSimpleCommand(ctx, e.factory, e.logger, "btrfs", "subvolume", "snapshot", "-r", src, destPath); err != nil {
			e.logger.Error("Failed to create btrfs snapshot", "src", src, "dest", destPath, "error", err)
			return err
		}
	}

	if err := runSimpleCommand(ctx, e.factory, e.logger, "restic", "version"); err != nil {
		return err
	}

	if err := runSimpleCommand(ctx, e.factory, e.logger, "restic", "backup", "--exclude-caches", e.cfg.BtrfsSnapshotsRoot); err != nil {
		e.logger.Error("Restic backup of btrfs snapshots failed", "error", err)
		_ = runSimpleCommand(ctx, e.factory, e.logger, "bash", "-c", deleteCmd)
		return err
	}

	_ = runSimpleCommand(ctx, e.factory, e.logger, "bash", "-c", deleteCmd)
	return nil
}
