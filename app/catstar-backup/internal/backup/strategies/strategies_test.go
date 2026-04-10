package strategies

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

// MockCommandExecutor captures the commands that would be run
// and optionally returns predefined errors for testing failure paths.
type MockCommandExecutor struct {
	ExecutedCommands []string
	FailOnCommand    string
}

func (m *MockCommandExecutor) Execute(ctx context.Context, cmdStr string, args ...string) ([]byte, error) {
	fullCmd := cmdStr + " " + strings.Join(args, " ")
	m.ExecutedCommands = append(m.ExecutedCommands, fullCmd)
	
	if m.FailOnCommand != "" && strings.Contains(fullCmd, m.FailOnCommand) {
		return []byte("mock error output"), fmt.Errorf("mock error for %s", fullCmd)
	}
	return []byte("mock success output"), nil
}

func createTestDeps() (*config.AppConfig, *slog.Logger, *notify.CompositeNotifier) {
	cfg := &config.AppConfig{
		MachineName:        "TestHost",
		NotifySendVerbose:  false,
		ResticRoot:         "/data",
		TarSSHServer:       "user@host",
		TarOpenSSLType:     "aes-128-cbc",
		TarOpenSSLPassword: "password",
		BtrfsSnapshotsRoot: "/snapshots",
		BtrfsSnapshots: map[string]string{
			"root": "/",
		},
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	notifier := notify.NewCompositeNotifier(cfg, logger)
	return cfg, logger, notifier
}

func TestResticEngine_Success(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockExec := &MockCommandExecutor{}
	engine := NewResticEngine(cfg, logger, notifier, mockExec)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if len(mockExec.ExecutedCommands) != 2 {
		t.Fatalf("expected 2 commands, got %d", len(mockExec.ExecutedCommands))
	}
	if !strings.Contains(mockExec.ExecutedCommands[1], "restic backup") {
		t.Errorf("expected restic backup command, got %s", mockExec.ExecutedCommands[1])
	}
}

func TestTarSSHEngine_Success(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockExec := &MockCommandExecutor{}
	engine := NewTarSSHEngine(cfg, logger, notifier, mockExec)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	if len(mockExec.ExecutedCommands) != 1 {
		t.Fatalf("expected 1 command, got %d", len(mockExec.ExecutedCommands))
	}
	if !strings.Contains(mockExec.ExecutedCommands[0], "tar -I zstd") {
		t.Errorf("expected tar command, got %s", mockExec.ExecutedCommands[0])
	}
}

func TestBtrfsResticEngine_Success(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockExec := &MockCommandExecutor{}
	engine := NewBtrfsResticEngine(cfg, logger, notifier, mockExec)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}

	// 1. delete old, 2. create snapshot, 3. restic version, 4. restic backup, 5. delete new
	if len(mockExec.ExecutedCommands) != 5 {
		t.Fatalf("expected 5 commands, got %d:\n%v", len(mockExec.ExecutedCommands), mockExec.ExecutedCommands)
	}
}

func TestBtrfsResticEngine_FailureCleanup(t *testing.T) {
	cfg, logger, notifier := createTestDeps()
	mockExec := &MockCommandExecutor{
		FailOnCommand: "restic backup", // Simulate restic failure
	}
	engine := NewBtrfsResticEngine(cfg, logger, notifier, mockExec)

	err := engine.Execute(context.Background())
	if err == nil {
		t.Fatalf("expected failure, got nil")
	}

	// Even if it failed on restic backup (command #4), it should still trigger
	// the cleanup command (command #5)
	if len(mockExec.ExecutedCommands) != 5 {
		t.Fatalf("expected 5 commands (including cleanup), got %d", len(mockExec.ExecutedCommands))
	}
	if !strings.Contains(mockExec.ExecutedCommands[4], "btrfs subvolume delete") {
		t.Errorf("expected final command to be cleanup, got %s", mockExec.ExecutedCommands[4])
	}
}
