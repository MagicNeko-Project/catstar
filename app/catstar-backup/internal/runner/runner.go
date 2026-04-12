package runner

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"slices"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/backup"
	"github.com/MagicNeko-Project/catstar-backup/internal/backup/strategies"
	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
	"github.com/MagicNeko-Project/catstar-backup/internal/observability"
)

// App manages the lifecycle, orchestration, and teardown of the backup system.
type App struct {
	cfg       *config.Config
	logger    *slog.Logger
	telemetry *observability.TelemetryClient
	notifier  *notify.CompositeNotifier
	logBuffer *observability.LogBuffer
	engines   []backup.Engine
	clock     clock.Provider
}

// NewApp wires together all dependencies and builds the execution plan based on the config.
func NewApp(cfg *config.Config, outStream io.Writer, clk clock.Provider) (*App, error) {
	logBuffer := observability.NewLogBuffer()
	multiWriter := io.MultiWriter(outStream, logBuffer)

	var logLevel slog.Level
	if err := logLevel.UnmarshalText([]byte(cfg.App.LogLevel)); err != nil {
		logLevel = slog.LevelInfo
	}

	logger := slog.New(slog.NewTextHandler(multiWriter, &slog.HandlerOptions{Level: logLevel}))

	// Create dedicated HTTP clients
	httpClient := &http.Client{Timeout: 15 * time.Second}
	notifyClient := &http.Client{Timeout: 10 * time.Second}

	telemetryClient := observability.NewTelemetryClient(cfg, httpClient)
	notifier := notify.NewCompositeNotifier(cfg, logger, notifyClient)
	factory := strategies.NewDefaultCommandFactory(logger)

	var engines []backup.Engine

	for _, job := range cfg.Jobs {
		machine := cfg.App.MachineName
		verbose := cfg.Notifications.SendVerbose

		switch job.Type {
		case "test":
			engines = append(engines, strategies.NewTestEngine(job.Name, machine, verbose, logger, notifier))
		case "tar_ssh":
			if job.TarSSH == nil {
				return nil, fmt.Errorf("job %q is missing tar_ssh configuration block", job.Name)
			}
			engines = append(engines, strategies.NewTarSSHEngine(job.Name, machine, verbose, job.TarSSH, logger, notifier, factory))
		case "restic":
			if job.Restic == nil {
				return nil, fmt.Errorf("job %q is missing restic configuration block", job.Name)
			}
			engines = append(engines, strategies.NewResticEngine(job.Name, machine, verbose, job.Restic, logger, notifier, factory))
		case "btrfs_restic":
			if job.BtrfsRestic == nil {
				return nil, fmt.Errorf("job %q is missing btrfs_restic configuration block", job.Name)
			}
			engines = append(engines, strategies.NewBtrfsResticEngine(job.Name, machine, verbose, job.BtrfsRestic, logger, notifier, factory))
		default:
			return nil, fmt.Errorf("unknown job type: %q", job.Type)
		}
	}

	return &App{
		cfg:       cfg,
		logger:    logger,
		telemetry: telemetryClient,
		notifier:  notifier,
		logBuffer: logBuffer,
		engines:   engines,
		clock:     clk,
	}, nil
}

// Run executes the application logic and returns an appropriate OS exit code.
func (a *App) Run(ctx context.Context) int {
	if len(a.engines) == 0 {
		a.logger.Warn("No backup jobs configured. Exiting.")
		return 0
	}

	orchestrator := backup.NewOrchestrator(a.cfg, a.logger, a.notifier, a.engines)

	backupBegin := a.clock.Now()

	// Send Start Ping
	if a.cfg.Telemetry.PingStartURL != "" {
		startMsg := fmt.Sprintf("%s 开始备份时间: %s", a.cfg.App.MachineName, backupBegin.Format(time.RFC3339))
		if err := a.telemetry.PingStart(ctx, startMsg); err != nil {
			a.logger.Error("Failed to send start ping", "error", err)
		}
	}

	// Execute the backup plan
	runErr := orchestrator.Run(ctx)

	backupEnd := a.clock.Now()

	// Post-Run Telemetry & Notifications
	statusCode := 0
	if runErr != nil {
		statusCode = 1
	}

	finalLogText := fmt.Sprintf("Catstar - 喵星备份日志\n%s\n=================================\n", a.logBuffer.String())

	// Send End Ping
	if a.cfg.Telemetry.PingEndURL != "" {
		if err := a.telemetry.PingEnd(ctx, statusCode, finalLogText); err != nil {
			a.logger.Error("Failed to send end ping", "error", err)
		}
	}

	if runErr != nil {
		// Handle Failure
		journalLink := a.telemetry.UploadLogs(ctx, finalLogText)

		msg := fmt.Sprintf("%s 备份失败❌！\n错误码：%d\n开始：%s\n结束：%s\n%s",
			a.cfg.App.MachineName,
			statusCode,
			backupBegin.Format("2006-01-02 15:04:05"),
			backupEnd.Format("2006-01-02 15:04:05"),
			journalLink,
		)
		a.notifier.Send(ctx, msg)
		a.logger.Error("Backup completed with errors", "duration", backupEnd.Sub(backupBegin))
		return statusCode

	} else if a.cfg.Notifications.SendSummary {
		// Handle Success
		shouldSend := len(a.cfg.Notifications.SummaryHours) == 0
		if !shouldSend {
			shouldSend = slices.Contains(a.cfg.Notifications.SummaryHours, backupEnd.Hour())
		}

		if shouldSend {
			journalLink := a.telemetry.UploadLogs(ctx, finalLogText)
			msg := fmt.Sprintf("%s 备份完成✅\n开始：%s\n结束：%s\n%s",
				a.cfg.App.MachineName,
				backupBegin.Format("2006-01-02 15:04:05"),
				backupEnd.Format("2006-01-02 15:04:05"),
				journalLink,
			)
			a.notifier.SendSummary(ctx, msg)
		}
		a.logger.Info("Backup completed successfully", "duration", backupEnd.Sub(backupBegin))
	}

	return 0
}
