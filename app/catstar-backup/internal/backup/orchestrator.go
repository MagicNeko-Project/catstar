package backup

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

// Engine defines the contract for executing a backup strategy.
type Engine interface {
	Name() string
	Execute(ctx context.Context) error
}

// Orchestrator coordinates sequential execution of backup engines.
type Orchestrator struct {
	config        *config.Config
	logger        *slog.Logger
	notifier      *notify.CompositeNotifier
	engines       []Engine
	clockProvider clock.Provider
}

// NewOrchestrator constructs an orchestrator with configured engines and clock provider.
func NewOrchestrator(
	configuration *config.Config,
	logger *slog.Logger,
	notifier *notify.CompositeNotifier,
	engines []Engine,
	clockProvider clock.Provider,
) *Orchestrator {
	return &Orchestrator{
		config:        configuration,
		logger:        logger,
		notifier:      notifier,
		engines:       engines,
		clockProvider: clockProvider,
	}
}

// Run executes all configured engines sequentially, aggregating any encountered errors.
func (orchestrator *Orchestrator) Run(ctx context.Context) error {
	orchestrator.logger.Info("Starting backup orchestration")

	if orchestrator.config.Notifications.SendVerbose {
		startTimestamp := orchestrator.clockProvider.Now().Format("2006-01-02 15:04:05")
		startMessage := fmt.Sprintf("%s 开始备份时间: %s", orchestrator.config.App.MachineName, startTimestamp)
		orchestrator.notifier.Send(ctx, startMessage)
	}

	var accumulatedErrors []error

	for _, engine := range orchestrator.engines {
		orchestrator.logger.Info("Executing engine", "engine", engine.Name())

		if err := engine.Execute(ctx); err != nil {
			orchestrator.logger.Error("Engine execution failed",
				"engine", engine.Name(),
				"error", err,
			)
			accumulatedErrors = append(accumulatedErrors, fmt.Errorf("engine %s failed: %w", engine.Name(), err))
		}
	}

	if orchestrator.config.Notifications.SendVerbose {
		endTimestamp := orchestrator.clockProvider.Now().Format("2006-01-02 15:04:05")
		endMessage := fmt.Sprintf("%s 结束备份时间: %s", orchestrator.config.App.MachineName, endTimestamp)
		orchestrator.notifier.Send(ctx, endMessage)
	}

	if len(accumulatedErrors) > 0 {
		return errors.Join(accumulatedErrors...)
	}

	return nil
}
