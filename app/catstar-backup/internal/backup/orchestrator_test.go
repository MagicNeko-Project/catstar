package backup

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"testing"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

type MockEngine struct {
	name       string
	shouldFail bool
	executed   bool
}

func (mock *MockEngine) Name() string { return mock.name }

func (mock *MockEngine) Execute(ctx context.Context) error {
	mock.executed = true
	if mock.shouldFail {
		return fmt.Errorf("mock engine %s failure", mock.name)
	}
	return nil
}

func TestOrchestrator_Run(t *testing.T) {
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
	mockClock := clock.NewMockClock(time.Date(2026, 8, 29, 12, 0, 0, 0, time.UTC))

	t.Run("All Engines Succeed", func(subtest *testing.T) {
		engineA := &MockEngine{name: "EngineA"}
		engineB := &MockEngine{name: "EngineB"}

		orchestrator := NewOrchestrator(testConfig, discardLogger, compositeNotifier, []Engine{engineA, engineB}, mockClock)

		if err := orchestrator.Run(context.Background()); err != nil {
			subtest.Fatalf("expected success, got %v", err)
		}
		if !engineA.executed || !engineB.executed {
			subtest.Fatalf("not all engines executed")
		}
	})

	t.Run("Engine Fails", func(subtest *testing.T) {
		engineA := &MockEngine{name: "EngineA", shouldFail: true}
		engineB := &MockEngine{name: "EngineB"}

		orchestrator := NewOrchestrator(testConfig, discardLogger, compositeNotifier, []Engine{engineA, engineB}, mockClock)

		err := orchestrator.Run(context.Background())
		if err == nil {
			subtest.Fatalf("expected error due to engine failure, got nil")
		}

		if !engineA.executed || !engineB.executed {
			subtest.Fatalf("expected all engines to execute even if one fails")
		}
	})
}
