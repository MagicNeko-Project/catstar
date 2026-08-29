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

const (
	defaultTelemetryTimeout    = 15 * time.Second
	defaultNotificationTimeout = 10 * time.Second
)

// App manages the lifecycle, orchestration, and execution of backup operations.
type App struct {
	config        *config.Config
	logger        *slog.Logger
	telemetry     *observability.TelemetryClient
	notifier      *notify.CompositeNotifier
	logBuffer     *observability.LogBuffer
	engines       []backup.Engine
	clockProvider clock.Provider
}

// NewApp wires together dependencies and initializes the backup execution plan.
func NewApp(configuration *config.Config, outputStream io.Writer, clockProvider clock.Provider) (*App, error) {
	logBuffer := observability.NewLogBuffer()
	multiWriter := io.MultiWriter(outputStream, logBuffer)

	var logLevel slog.Level
	if err := logLevel.UnmarshalText([]byte(configuration.App.LogLevel)); err != nil {
		logLevel = slog.LevelInfo
	}

	logger := slog.New(slog.NewTextHandler(multiWriter, &slog.HandlerOptions{Level: logLevel}))

	telemetryHTTPClient := &http.Client{Timeout: defaultTelemetryTimeout}
	notificationHTTPClient := &http.Client{Timeout: defaultNotificationTimeout}

	telemetryClient := observability.NewTelemetryClient(configuration, telemetryHTTPClient)
	compositeNotifier := notify.NewCompositeNotifier(configuration, logger, notificationHTTPClient)
	commandFactory := strategies.NewDefaultCommandFactory(logger)

	var engines []backup.Engine

	for _, job := range configuration.Jobs {
		machineName := configuration.App.MachineName
		sendVerbose := configuration.Notifications.SendVerbose

		switch config.StrategyType(job.Type) {
		case config.StrategyTypeTest:
			engines = append(engines, strategies.NewTestEngine(job.Name, machineName, sendVerbose, logger, compositeNotifier))
		case config.StrategyTypeTarSSH:
			if job.TarSSH == nil {
				return nil, fmt.Errorf("job %q is missing tar_ssh configuration block", job.Name)
			}
			engines = append(engines, strategies.NewTarSSHEngine(job.Name, machineName, sendVerbose, job.TarSSH, logger, compositeNotifier, commandFactory, clockProvider))
		case config.StrategyTypeRestic:
			if job.Restic == nil {
				return nil, fmt.Errorf("job %q is missing restic configuration block", job.Name)
			}
			engines = append(engines, strategies.NewResticEngine(job.Name, machineName, sendVerbose, job.Restic, logger, compositeNotifier, commandFactory))
		case config.StrategyTypeBtrfsRestic:
			if job.BtrfsRestic == nil {
				return nil, fmt.Errorf("job %q is missing btrfs_restic configuration block", job.Name)
			}
			engines = append(engines, strategies.NewBtrfsResticEngine(job.Name, machineName, sendVerbose, job.BtrfsRestic, logger, compositeNotifier, commandFactory))
		default:
			return nil, fmt.Errorf("unknown job type: %q", job.Type)
		}
	}

	return &App{
		config:        configuration,
		logger:        logger,
		telemetry:     telemetryClient,
		notifier:      compositeNotifier,
		logBuffer:     logBuffer,
		engines:       engines,
		clockProvider: clockProvider,
	}, nil
}

// Run executes configured backup operations and returns an application exit status code.
func (app *App) Run(ctx context.Context) int {
	if len(app.engines) == 0 {
		app.logger.Warn("No backup jobs configured. Exiting.")
		return 0
	}

	orchestrator := backup.NewOrchestrator(app.config, app.logger, app.notifier, app.engines, app.clockProvider)

	backupStartTime := app.clockProvider.Now()

	if app.config.Telemetry.PingStartURL != "" {
		startMessage := fmt.Sprintf("%s 开始备份时间: %s", app.config.App.MachineName, backupStartTime.Format(time.RFC3339))
		if err := app.telemetry.PingStart(ctx, startMessage); err != nil {
			app.logger.Error("Failed to send start ping", "error", err)
		}
	}

	executionError := orchestrator.Run(ctx)

	backupEndTime := app.clockProvider.Now()

	statusCode := 0
	if executionError != nil {
		statusCode = 1
	}

	finalLogContent := fmt.Sprintf("Catstar - 喵星备份日志\n%s\n=================================\n", app.logBuffer.String())

	if app.config.Telemetry.PingEndURL != "" {
		if err := app.telemetry.PingEnd(ctx, statusCode, finalLogContent); err != nil {
			app.logger.Error("Failed to send end ping", "error", err)
		}
	}

	if executionError != nil {
		journalLink := app.telemetry.UploadLogs(ctx, finalLogContent)
		failureMessage := fmt.Sprintf("%s 备份失败❌！\n错误码：%d\n开始：%s\n结束：%s\n%s",
			app.config.App.MachineName,
			statusCode,
			backupStartTime.Format("2006-01-02 15:04:05"),
			backupEndTime.Format("2006-01-02 15:04:05"),
			journalLink,
		)
		app.notifier.Send(ctx, failureMessage)
		app.logger.Error("Backup completed with errors", "duration", backupEndTime.Sub(backupStartTime), "error", executionError)
		return statusCode
	}

	if app.config.Notifications.SendSummary {
		shouldSendSummary := len(app.config.Notifications.SummaryHours) == 0 || slices.Contains(app.config.Notifications.SummaryHours, backupEndTime.Hour())

		if shouldSendSummary {
			journalLink := app.telemetry.UploadLogs(ctx, finalLogContent)
			successMessage := fmt.Sprintf("%s 备份完成✅\n开始：%s\n结束：%s\n%s",
				app.config.App.MachineName,
				backupStartTime.Format("2006-01-02 15:04:05"),
				backupEndTime.Format("2006-01-02 15:04:05"),
				journalLink,
			)
			app.notifier.SendSummary(ctx, successMessage)
		}
		app.logger.Info("Backup completed successfully", "duration", backupEndTime.Sub(backupStartTime))
	}

	return 0
}
