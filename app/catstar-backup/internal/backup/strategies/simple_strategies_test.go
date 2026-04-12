package strategies

import (
	"context"
	"io"
	"log/slog"
	"strings"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

func createTestDeps() (*config.Config, *slog.Logger, *notify.CompositeNotifier) {
	cfg := &config.Config{
		App: config.AppConfig{
			MachineName: "TestHost",
		},
		Notifications: config.NotificationsConfig{
			SendVerbose: false,
		},
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	notifier := notify.NewCompositeNotifier(cfg, logger)
	return cfg, logger, notifier
}

func TestResticEngine_Success(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockFactory := &MockCommandFactory{}
	jobCfg := &config.ResticConfig{
		Root: "/data",
	}
	engine := NewResticEngine("restic_job", cfg.App.MachineName, cfg.Notifications.SendVerbose, jobCfg, logger, notifier, mockFactory)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if len(mockFactory.Processes) != 2 {
		t.Fatalf("expected 2 commands, got %d", len(mockFactory.Processes))
	}
	if !strings.Contains(mockFactory.Processes[1].FullCmd, "restic backup") {
		t.Errorf("expected restic backup command, got %s", mockFactory.Processes[1].FullCmd)
	}
}

func TestBtrfsResticEngine_Success(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockFactory := &MockCommandFactory{}
	jobCfg := &config.BtrfsResticConfig{
		SnapshotsRoot: "/snapshots",
		Subvolumes: map[string]string{
			"root": "/",
		},
	}
	engine := NewBtrfsResticEngine("btrfs_job", cfg.App.MachineName, cfg.Notifications.SendVerbose, jobCfg, logger, notifier, mockFactory)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if len(mockFactory.Processes) != 5 {
		t.Fatalf("expected 5 commands, got %d", len(mockFactory.Processes))
	}
}

func TestBtrfsResticEngine_FailureCleanup(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockFactory := &MockCommandFactory{
		FailOnCreate: "restic backup", // Note: The factory matches the initial command name.
		// If we want to fail `restic backup` but allow `restic version`, we'd have to extend MockCommandFactory. 
		// For simplicity, failing "restic" altogether tests the deferred cleanup.
	}
	mockFactory.FailOnCreate = "restic"

	jobCfg := &config.BtrfsResticConfig{
		SnapshotsRoot: "/snapshots",
		Subvolumes: map[string]string{
			"root": "/",
		},
	}
	engine := NewBtrfsResticEngine("btrfs_job", cfg.App.MachineName, cfg.Notifications.SendVerbose, jobCfg, logger, notifier, mockFactory)

	err := engine.Execute(context.Background())
	if err == nil {
		t.Fatalf("expected failure, got nil")
	}

	// Should still have attempted cleanup (the last command created)
	lastCmd := mockFactory.Processes[len(mockFactory.Processes)-1].FullCmd
	if !strings.Contains(lastCmd, "btrfs subvolume delete") {
		t.Errorf("expected final command to be cleanup, got %s", lastCmd)
	}
}
