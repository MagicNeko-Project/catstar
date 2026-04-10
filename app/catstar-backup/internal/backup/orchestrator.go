package backup

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

// Engine defines the interface for a specific backup strategy.
type Engine interface {
	Name() string
	Execute(ctx context.Context) error
}

// Orchestrator manages the lifecycle of multiple backup engines.
type Orchestrator struct {
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	engines  []Engine
}

// NewOrchestrator wires up the requested backup strategies.
func NewOrchestrator(cfg *config.AppConfig, logger *slog.Logger, n *notify.CompositeNotifier, engines []Engine) *Orchestrator {
	return &Orchestrator{
		cfg:      cfg,
		logger:   logger,
		notifier: n,
		engines:  engines,
	}
}

// Run executes all configured engines sequentially.
func (o *Orchestrator) Run(ctx context.Context) error {
	o.logger.Info("Starting backup orchestration")
	
	if o.cfg.NotifySendVerbose {
		msg := fmt.Sprintf("%s 开始备份时间: %s", o.cfg.MachineName, "TODO_TIME")
		o.notifier.Send(ctx, msg)
	}

	var hasErrors bool

	for _, engine := range o.engines {
		o.logger.Info("Executing engine", "engine", engine.Name())
		
		if err := engine.Execute(ctx); err != nil {
			o.logger.Error("Engine execution failed", 
				"engine", engine.Name(), 
				"error", err,
			)
			hasErrors = true
			// Depending on requirements, we might want to continue to the next engine even if one fails.
			// For now, we continue and mark the overall run as having errors.
		}
	}

	if o.cfg.NotifySendVerbose {
		msg := fmt.Sprintf("%s 结束备份时间: %s", o.cfg.MachineName, "TODO_TIME")
		o.notifier.Send(ctx, msg)
	}

	if hasErrors {
		return fmt.Errorf("one or more backup engines failed")
	}

	return nil
}
