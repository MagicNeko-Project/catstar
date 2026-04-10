package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/backup"
	"github.com/MagicNeko-Project/catstar-backup/internal/backup/strategies"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
	"github.com/MagicNeko-Project/catstar-backup/internal/observability"
)

func main() {
	// 1. Load Configuration
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load configuration: %v\n", err)
		os.Exit(1)
	}

	// 2. Initialize Telemetry & Logging
	logBuffer := observability.NewLogBuffer()
	
	// Create a multi-writer to send logs to both stdout and our in-memory buffer
	multiWriter := io.MultiWriter(os.Stdout, logBuffer)
	
	// Use slog for structured, leveled logging
	logger := slog.New(slog.NewTextHandler(multiWriter, &slog.HandlerOptions{
		Level: slog.LevelDebug, // Or based on a config flag
	}))
	slog.SetDefault(logger)

	telemetryClient := observability.NewTelemetryClient(cfg)

	// 3. Initialize Notifiers
	notifier := notify.NewCompositeNotifier(cfg, logger)

	// 4. Initialize Backup Engines
	var engines []backup.Engine

	if cfg.BackupTest {
		engines = append(engines, strategies.NewTestEngine(cfg, logger, notifier))
	}
	if cfg.TarSSHServer != "" {
		engines = append(engines, strategies.NewTarSSHEngine(cfg, logger, notifier))
	}
	if cfg.ResticRoot != "" {
		engines = append(engines, strategies.NewResticEngine(cfg, logger, notifier))
	}
	if cfg.BtrfsSnapshotsRoot != "" {
		engines = append(engines, strategies.NewBtrfsResticEngine(cfg, logger, notifier))
	}

	if len(engines) == 0 {
		logger.Warn("No backup strategies configured. Exiting.")
		os.Exit(0)
	}

	// 5. Build and Run Orchestrator
	orchestrator := backup.NewOrchestrator(cfg, logger, notifier, engines)

	// Global context with a safety timeout (e.g., 12 hours)
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Hour)
	defer cancel()

	backupBegin := time.Now()
	
	// Send Start Ping
	if cfg.HTTPPingStartURL != "" {
		startMsg := fmt.Sprintf("%s 开始备份时间: %s", cfg.MachineName, backupBegin.Format(time.RFC3339))
		if err := telemetryClient.PingStart(ctx, startMsg); err != nil {
			logger.Error("Failed to send start ping", "error", err)
		}
	}

	// Execute the backup plan
	runErr := orchestrator.Run(ctx)

	backupEnd := time.Now()

	// 6. Post-Run Telemetry & Notifications
	statusCode := 0
	if runErr != nil {
		statusCode = 1
	}

	// Prepare the final log text (similar to print_journal)
	finalLogText := fmt.Sprintf("Catstar - 喵星备份日志\n%s\n=================================\n", logBuffer.String())

	// Send End Ping
	if cfg.HTTPPingURL != "" {
		if err := telemetryClient.PingEnd(ctx, statusCode, finalLogText); err != nil {
			logger.Error("Failed to send end ping", "error", err)
		}
	}

	// Resolution & Upload
	if runErr != nil {
		// Handle Failure
		journalLink := telemetryClient.UploadLogs(ctx, finalLogText)
		
		msg := fmt.Sprintf("%s 备份失败❌！\n错误码：%d\n开始：%s\n结束：%s\n%s",
			cfg.MachineName,
			statusCode,
			backupBegin.Format("2006-01-02 15:04:05"),
			backupEnd.Format("2006-01-02 15:04:05"),
			journalLink,
		)
		notifier.Send(ctx, msg)
		logger.Error("Backup completed with errors", "duration", backupEnd.Sub(backupBegin))
		os.Exit(statusCode)
		
	} else if cfg.NotifySendSummary {
		// Handle Success (if summary is enabled and within the time window)
		shouldSend := len(cfg.NotifySendSummaryHours) == 0
		if !shouldSend {
			currentHour := time.Now().Hour()
			for _, h := range cfg.NotifySendSummaryHours {
				if currentHour == h {
					shouldSend = true
					break
				}
			}
		}

		if shouldSend {
			journalLink := telemetryClient.UploadLogs(ctx, finalLogText)
			msg := fmt.Sprintf("%s 备份完成✅\n开始：%s\n结束：%s\n%s",
				cfg.MachineName,
				backupBegin.Format("2006-01-02 15:04:05"),
				backupEnd.Format("2006-01-02 15:04:05"),
				journalLink,
			)
			notifier.SendSummary(ctx, msg)
		}
		logger.Info("Backup completed successfully", "duration", backupEnd.Sub(backupBegin))
	}
}
