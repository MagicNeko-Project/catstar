package strategies

import (
	"context"
	"fmt"
	"log/slog"
	"maps"
	"slices"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

// ----------------------------------------------------------------------------
// Test Engine
// ----------------------------------------------------------------------------

type TestEngine struct {
	jobName     string
	machineName string
	verbose     bool
	logger      *slog.Logger
	notifier    *notify.CompositeNotifier
}

func NewTestEngine(
	jobName string,
	machineName string,
	verbose bool,
	logger *slog.Logger,
	notifier *notify.CompositeNotifier,
) *TestEngine {
	return &TestEngine{
		jobName:     jobName,
		machineName: machineName,
		verbose:     verbose,
		logger:      logger.With("job", jobName),
		notifier:    notifier,
	}
}

func (engine *TestEngine) Name() string { return engine.jobName }

func (engine *TestEngine) Execute(ctx context.Context) error {
	engine.logger.Info("Executing Test Backup Engine")
	if engine.verbose {
		engine.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：测试，只输出消息", engine.machineName, engine.jobName))
	}

	for stepIndex := 1; stepIndex <= 2; stepIndex++ {
		engine.logger.Info(fmt.Sprintf("测试备份消息：123*%d", stepIndex))
	}

	return nil
}

// ----------------------------------------------------------------------------
// Restic Engine
// ----------------------------------------------------------------------------

type ResticEngine struct {
	jobName        string
	machineName    string
	verbose        bool
	config         *config.ResticConfig
	logger         *slog.Logger
	notifier       *notify.CompositeNotifier
	commandFactory CommandFactory
}

func NewResticEngine(
	jobName string,
	machineName string,
	verbose bool,
	resticConfig *config.ResticConfig,
	logger *slog.Logger,
	notifier *notify.CompositeNotifier,
	commandFactory CommandFactory,
) *ResticEngine {
	return &ResticEngine{
		jobName:        jobName,
		machineName:    machineName,
		verbose:        verbose,
		config:         resticConfig,
		logger:         logger.With("job", jobName),
		notifier:       notifier,
		commandFactory: commandFactory,
	}
}

func (engine *ResticEngine) Name() string { return engine.jobName }

func (engine *ResticEngine) Execute(ctx context.Context) error {
	engine.logger.Info("Executing Restic Backup Engine")
	if engine.verbose {
		engine.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：restic", engine.machineName, engine.jobName))
	}

	if err := runSimpleCommand(ctx, engine.commandFactory, engine.logger, "restic", "version"); err != nil {
		return fmt.Errorf("restic version check failed: %w", err)
	}

	if err := runSimpleCommand(ctx, engine.commandFactory, engine.logger, "restic", "backup", "--exclude-caches", "--one-file-system", engine.config.Root); err != nil {
		return fmt.Errorf("restic backup failed: %w", err)
	}

	return nil
}

// ----------------------------------------------------------------------------
// BTRFS Restic Engine
// ----------------------------------------------------------------------------

type BtrfsResticEngine struct {
	jobName        string
	machineName    string
	verbose        bool
	config         *config.BtrfsResticConfig
	logger         *slog.Logger
	notifier       *notify.CompositeNotifier
	commandFactory CommandFactory
}

func NewBtrfsResticEngine(
	jobName string,
	machineName string,
	verbose bool,
	btrfsResticConfig *config.BtrfsResticConfig,
	logger *slog.Logger,
	notifier *notify.CompositeNotifier,
	commandFactory CommandFactory,
) *BtrfsResticEngine {
	return &BtrfsResticEngine{
		jobName:        jobName,
		machineName:    machineName,
		verbose:        verbose,
		config:         btrfsResticConfig,
		logger:         logger.With("job", jobName),
		notifier:       notifier,
		commandFactory: commandFactory,
	}
}

func (engine *BtrfsResticEngine) Name() string { return engine.jobName }

func (engine *BtrfsResticEngine) Execute(ctx context.Context) error {
	engine.logger.Info("Executing BTRFS Restic Backup Engine")
	if engine.verbose {
		engine.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：btrfs 子卷快照 + restic", engine.machineName, engine.jobName))
	}

	deleteCommand := fmt.Sprintf("btrfs subvolume delete %s/* || true", engine.config.SnapshotsRoot)

	_ = runSimpleCommand(ctx, engine.commandFactory, engine.logger, "bash", "-c", deleteCommand)

	defer func() {
		_ = runSimpleCommand(context.Background(), engine.commandFactory, engine.logger, "bash", "-c", deleteCommand)
	}()

	sortedSubvolumeKeys := slices.Sorted(maps.Keys(engine.config.Subvolumes))
	for _, destinationSubvolumeKey := range sortedSubvolumeKeys {
		sourceSubvolumePath := engine.config.Subvolumes[destinationSubvolumeKey]
		destinationSnapshotPath := fmt.Sprintf("%s/%s", engine.config.SnapshotsRoot, destinationSubvolumeKey)

		if err := runSimpleCommand(ctx, engine.commandFactory, engine.logger, "btrfs", "subvolume", "snapshot", "-r", sourceSubvolumePath, destinationSnapshotPath); err != nil {
			engine.logger.Error("Failed to create btrfs snapshot", "source", sourceSubvolumePath, "destination", destinationSnapshotPath, "error", err)
			return fmt.Errorf("btrfs snapshot creation failed for %s: %w", destinationSnapshotPath, err)
		}
	}

	if err := runSimpleCommand(ctx, engine.commandFactory, engine.logger, "restic", "version"); err != nil {
		return fmt.Errorf("restic version check failed: %w", err)
	}

	if err := runSimpleCommand(ctx, engine.commandFactory, engine.logger, "restic", "backup", "--exclude-caches", engine.config.SnapshotsRoot); err != nil {
		engine.logger.Error("Restic backup of btrfs snapshots failed", "error", err)
		return fmt.Errorf("restic backup of btrfs snapshots failed: %w", err)
	}

	return nil
}
