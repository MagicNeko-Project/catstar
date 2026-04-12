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
	jobName  string
	machine  string
	verbose  bool
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
}

func NewTestEngine(jobName, machineName string, verbose bool, logger *slog.Logger, notifier *notify.CompositeNotifier) *TestEngine {
	return &TestEngine{jobName: jobName, machine: machineName, verbose: verbose, logger: logger.With("job", jobName), notifier: notifier}
}

func (e *TestEngine) Name() string { return e.jobName }

func (e *TestEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Test Backup Engine")
	if e.verbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：测试，只输出消息", e.machine, e.jobName))
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
	jobName  string
	machine  string
	verbose  bool
	cfg      *config.ResticConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	factory  CommandFactory
}

func NewResticEngine(jobName, machineName string, verbose bool, cfg *config.ResticConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, factory CommandFactory) *ResticEngine {
	return &ResticEngine{jobName: jobName, machine: machineName, verbose: verbose, cfg: cfg, logger: logger.With("job", jobName), notifier: notifier, factory: factory}
}

func (e *ResticEngine) Name() string { return e.jobName }

func (e *ResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Restic Backup Engine")
	if e.verbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：restic", e.machine, e.jobName))
	}

	if err := runSimpleCommand(ctx, e.factory, e.logger, "restic", "version"); err != nil {
		return err
	}

	return runSimpleCommand(ctx, e.factory, e.logger, "restic", "backup", "--exclude-caches", "--one-file-system", e.cfg.Root)
}

// ----------------------------------------------------------------------------
// BTRFS Restic Engine
// ----------------------------------------------------------------------------
type BtrfsResticEngine struct {
	jobName  string
	machine  string
	verbose  bool
	cfg      *config.BtrfsResticConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	factory  CommandFactory
}

func NewBtrfsResticEngine(jobName, machineName string, verbose bool, cfg *config.BtrfsResticConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, factory CommandFactory) *BtrfsResticEngine {
	return &BtrfsResticEngine{jobName: jobName, machine: machineName, verbose: verbose, cfg: cfg, logger: logger.With("job", jobName), notifier: notifier, factory: factory}
}

func (e *BtrfsResticEngine) Name() string { return e.jobName }

func (e *BtrfsResticEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing BTRFS Restic Backup Engine")
	if e.verbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：btrfs 子卷快照 + restic", e.machine, e.jobName))
	}

	deleteCmd := fmt.Sprintf("btrfs subvolume delete %s/* || true", e.cfg.SnapshotsRoot)
	
	// 1. Initial cleanup of lingering snapshots
	_ = runSimpleCommand(ctx, e.factory, e.logger, "bash", "-c", deleteCmd) 

	// ALWAYS attempt cleanup upon exit to prevent leaked btrfs subvolumes on disk
	defer func() {
		_ = runSimpleCommand(context.Background(), e.factory, e.logger, "bash", "-c", deleteCmd)
	}()

	for dest, src := range e.cfg.Subvolumes {
		destPath := fmt.Sprintf("%s/%s", e.cfg.SnapshotsRoot, dest)
		if err := runSimpleCommand(ctx, e.factory, e.logger, "btrfs", "subvolume", "snapshot", "-r", src, destPath); err != nil {
			e.logger.Error("Failed to create btrfs snapshot", "src", src, "dest", destPath, "error", err)
			return err
		}
	}

	if err := runSimpleCommand(ctx, e.factory, e.logger, "restic", "version"); err != nil {
		return err
	}

	if err := runSimpleCommand(ctx, e.factory, e.logger, "restic", "backup", "--exclude-caches", e.cfg.SnapshotsRoot); err != nil {
		e.logger.Error("Restic backup of btrfs snapshots failed", "error", err)
		return err
	}

	return nil
}
