package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"slices"
	"syscall"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/backup"
	"github.com/MagicNeko-Project/catstar-backup/internal/backup/strategies"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
	"github.com/MagicNeko-Project/catstar-backup/internal/observability"
)

func main() {
	configPath := flag.String("config", "catstar-backup.yaml", "Path to the YAML configuration file")
	flag.Parse()

	// 1. Load Configuration
	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load configuration: %v\n", err)
		os.Exit(1)
	}

	// 2. Initialize Telemetry & Logging
	logBuffer := observability.NewLogBuffer()
	
	multiWriter := io.MultiWriter(os.Stdout, logBuffer)
	
	var logLevel slog.Level
	if err := logLevel.UnmarshalText([]byte(cfg.App.LogLevel)); err != nil {
		logLevel = slog.LevelInfo
	}

	logger := slog.New(slog.NewTextHandler(multiWriter, &slog.HandlerOptions{
		Level: logLevel,
	}))
	slog.SetDefault(logger)

	telemetryClient := observability.NewTelemetryClient(cfg)

	// 3. Initialize Notifiers
	notifier := notify.NewCompositeNotifier(cfg, logger)

	// 4. Initialize Backup Engines Dynamically from Jobs Array
	var engines []backup.Engine
	factory := strategies.NewDefaultCommandFactory(logger)

	for _, job := range cfg.Jobs {
		machine := cfg.App.MachineName
		verbose := cfg.Notifications.SendVerbose

		switch job.Type {
		case "test":
			engines = append(engines, strategies.NewTestEngine(job.Name, machine, verbose, logger, notifier))
		case "tar_ssh":
			if job.TarSSH == nil {
				logger.Error("Job is missing tar_ssh configuration block", "job", job.Name)
				os.Exit(1)
			}
			engines = append(engines, strategies.NewTarSSHEngine(job.Name, machine, verbose, job.TarSSH, logger, notifier, factory))
		case "restic":
			if job.Restic == nil {
				logger.Error("Job is missing restic configuration block", "job", job.Name)
				os.Exit(1)
			}
			engines = append(engines, strategies.NewResticEngine(job.Name, machine, verbose, job.Restic, logger, notifier, factory))
		case "btrfs_restic":
			if job.BtrfsRestic == nil {
				logger.Error("Job is missing btrfs_restic configuration block", "job", job.Name)
				os.Exit(1)
			}
			engines = append(engines, strategies.NewBtrfsResticEngine(job.Name, machine, verbose, job.BtrfsRestic, logger, notifier, factory))
		}
	}

	if len(engines) == 0 {
		logger.Warn("No backup jobs configured. Exiting.")
		os.Exit(0)
	}

	// 5. Build and Run Orchestrator
	orchestrator := backup.NewOrchestrator(cfg, logger, notifier, engines)

	// Global context bound to OS signals for graceful shutdown
	ctx, cancelSignal := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancelSignal()

	ctx, cancelTimeout := context.WithTimeout(ctx, 12*time.Hour)
	defer cancelTimeout()

	backupBegin := time.Now()
	
	// Send Start Ping
	if cfg.Telemetry.PingStartURL != "" {
		startMsg := fmt.Sprintf("%s 开始备份时间: %s", cfg.App.MachineName, backupBegin.Format(time.RFC3339))
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

	finalLogText := fmt.Sprintf("Catstar - 喵星备份日志\n%s\n=================================\n", logBuffer.String())

	// Send End Ping
	if cfg.Telemetry.PingEndURL != "" {
		if err := telemetryClient.PingEnd(ctx, statusCode, finalLogText); err != nil {
			logger.Error("Failed to send end ping", "error", err)
		}
	}

	// Resolution & Upload
	if runErr != nil {
		// Handle Failure
		journalLink := telemetryClient.UploadLogs(ctx, finalLogText)
		
		msg := fmt.Sprintf("%s 备份失败❌！\n错误码：%d\n开始：%s\n结束：%s\n%s",
			cfg.App.MachineName,
			statusCode,
			backupBegin.Format("2006-01-02 15:04:05"),
			backupEnd.Format("2006-01-02 15:04:05"),
			journalLink,
		)
		notifier.Send(ctx, msg)
		logger.Error("Backup completed with errors", "duration", backupEnd.Sub(backupBegin))
		os.Exit(statusCode)
		
	} else if cfg.Notifications.SendSummary {
		// Handle Success (if summary is enabled and within the time window)
		shouldSend := len(cfg.Notifications.SummaryHours) == 0
		if !shouldSend {
			shouldSend = slices.Contains(cfg.Notifications.SummaryHours, time.Now().Hour())
		}

		if shouldSend {
			journalLink := telemetryClient.UploadLogs(ctx, finalLogText)
			msg := fmt.Sprintf("%s 备份完成✅\n开始：%s\n结束：%s\n%s",
				cfg.App.MachineName,
				backupBegin.Format("2006-01-02 15:04:05"),
				backupEnd.Format("2006-01-02 15:04:05"),
				journalLink,
			)
			notifier.SendSummary(ctx, msg)
		}
		logger.Info("Backup completed successfully", "duration", backupEnd.Sub(backupBegin))
	}
}
