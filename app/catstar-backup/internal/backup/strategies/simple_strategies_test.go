package strategies

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

func createTestDependencies() (*config.Config, *slog.Logger, *notify.CompositeNotifier) {
	testConfig := &config.Config{
		App: config.AppConfig{
			MachineName: "TestHost",
		},
		Notifications: config.NotificationsConfig{
			SendVerbose: true,
		},
	}
	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	dummyHTTP := &http.Client{}
	compositeNotifier := notify.NewCompositeNotifier(testConfig, discardLogger, dummyHTTP)
	return testConfig, discardLogger, compositeNotifier
}

func TestTestEngine_Success(t *testing.T) {
	testConfig, logger, notifier := createTestDependencies()
	testEngine := NewTestEngine("test_job", testConfig.App.MachineName, testConfig.Notifications.SendVerbose, logger, notifier)

	if testEngine.Name() != "test_job" {
		t.Fatalf("expected job name 'test_job', got %q", testEngine.Name())
	}

	if err := testEngine.Execute(context.Background()); err != nil {
		t.Fatalf("expected test engine execution to succeed, got %v", err)
	}
}

func TestResticEngine_Success(t *testing.T) {
	testConfig, logger, notifier := createTestDependencies()
	mockFactory := NewMockCommandFactory()
	resticConfig := &config.ResticConfig{
		Root: "/data",
	}
	engine := NewResticEngine("restic_job", testConfig.App.MachineName, testConfig.Notifications.SendVerbose, resticConfig, logger, notifier, mockFactory)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if len(mockFactory.Processes) != 2 {
		t.Fatalf("expected 2 commands, got %d", len(mockFactory.Processes))
	}
	if !strings.Contains(mockFactory.Processes[1].FullCommand, "restic backup") {
		t.Errorf("expected restic backup command, got %s", mockFactory.Processes[1].FullCommand)
	}
}

func TestBtrfsResticEngine_Success(t *testing.T) {
	testConfig, logger, notifier := createTestDependencies()
	mockFactory := NewMockCommandFactory()
	btrfsResticConfig := &config.BtrfsResticConfig{
		SnapshotsRoot: "/snapshots",
		Subvolumes: map[string]string{
			"root": "/",
		},
	}
	engine := NewBtrfsResticEngine("btrfs_job", testConfig.App.MachineName, testConfig.Notifications.SendVerbose, btrfsResticConfig, logger, notifier, mockFactory)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if len(mockFactory.Processes) != 5 {
		t.Fatalf("expected 5 commands, got %d", len(mockFactory.Processes))
	}
}

func TestBtrfsResticEngine_FailureCleanup(t *testing.T) {
	testConfig, logger, notifier := createTestDependencies()
	mockFactory := NewMockCommandFactory()
	mockFactory.FailOnCreate = "restic"

	btrfsResticConfig := &config.BtrfsResticConfig{
		SnapshotsRoot: "/snapshots",
		Subvolumes: map[string]string{
			"root": "/",
		},
	}
	engine := NewBtrfsResticEngine("btrfs_job", testConfig.App.MachineName, testConfig.Notifications.SendVerbose, btrfsResticConfig, logger, notifier, mockFactory)

	err := engine.Execute(context.Background())
	if err == nil {
		t.Fatalf("expected failure, got nil")
	}

	lastCommand := mockFactory.Processes[len(mockFactory.Processes)-1].FullCommand
	if !strings.Contains(lastCommand, "btrfs subvolume delete") {
		t.Errorf("expected final command to be cleanup, got %s", lastCommand)
	}
}
