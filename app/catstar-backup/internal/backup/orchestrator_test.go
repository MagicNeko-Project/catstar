package backup

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

type MockEngine struct {
	name        string
	shouldFail  bool
	executed    bool
}

func (m *MockEngine) Name() string { return m.name }
func (m *MockEngine) Execute(ctx context.Context) error {
	m.executed = true
	if m.shouldFail {
		return fmt.Errorf("mock engine %s failure", m.name)
	}
	return nil
}

func TestOrchestrator_Run(t *testing.T) {
	cfg := &config.AppConfig{
		MachineName:       "TestHost",
		NotifySendVerbose: false,
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	notifier := notify.NewCompositeNotifier(cfg, logger)

	t.Run("All Engines Succeed", func(t *testing.T) {
		e1 := &MockEngine{name: "Engine1"}
		e2 := &MockEngine{name: "Engine2"}

		orch := NewOrchestrator(cfg, logger, notifier, []Engine{e1, e2})

		if err := orch.Run(context.Background()); err != nil {
			t.Fatalf("expected success, got %v", err)
		}
		if !e1.executed || !e2.executed {
			t.Fatalf("not all engines executed")
		}
	})

	t.Run("Engine Fails", func(t *testing.T) {
		e1 := &MockEngine{name: "Engine1", shouldFail: true}
		e2 := &MockEngine{name: "Engine2"}

		orch := NewOrchestrator(cfg, logger, notifier, []Engine{e1, e2})

		err := orch.Run(context.Background())
		if err == nil {
			t.Fatalf("expected error due to engine failure, got nil")
		}

		// Currently, the orchestrator continues even if one fails. Let's verify both executed.
		if !e1.executed || !e2.executed {
			t.Fatalf("expected all engines to execute even if one fails")
		}
	})
}
