package runner

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

func TestApp_Run_Success(t *testing.T) {
	// Start a mock telemetry server
	var startHit, endHit bool
	var hitMu sync.Mutex

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hitMu.Lock()
		defer hitMu.Unlock()
		switch r.URL.Path {
		case "/ping/start":
			startHit = true
			w.WriteHeader(http.StatusOK)
		case "/ping/end/0":
			endHit = true
			w.WriteHeader(http.StatusOK)
		case "/upload":
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("https://paste.example.com/success"))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer ts.Close()

	// Generate a valid mock config
	cfg := &config.Config{
		App: config.AppConfig{
			MachineName: "TestRunnerHost",
			LogLevel:    "info",
		},
		Telemetry: config.TelemetryConfig{
			PingStartURL:     ts.URL + "/ping/start",
			PingEndURL:       ts.URL + "/ping/end",
			PingAppendStatus: true,
			JournalUploadURL: ts.URL + "/upload",
		},
		Notifications: config.NotificationsConfig{
			SendSummary: true,
			Debug: &config.DebugConfig{
				Enabled: true,
			},
		},
		Jobs: []config.JobConfig{
			{
				Name: "test_job",
				Type: "test",
			},
		},
	}

	// Define standard mock clock
	startTime := time.Date(2026, 5, 21, 10, 0, 0, 0, time.UTC)
	mockClock := clock.NewMockClock(startTime)

	// Run a separate goroutine to advance time concurrently to simulate duration
	go func() {
		time.Sleep(50 * time.Millisecond)
		mockClock.Advance(15 * time.Minute)
	}()

	var logBuf bytes.Buffer
	app, err := NewApp(cfg, &logBuf, mockClock)
	if err != nil {
		t.Fatalf("failed to initialize App: %v", err)
	}

	ctx := context.Background()
	exitCode := app.Run(ctx)

	if exitCode != 0 {
		t.Fatalf("expected exit code 0, got %d. Logs:\n%s", exitCode, logBuf.String())
	}

	hitMu.Lock()
	defer hitMu.Unlock()

	if !startHit {
		t.Error("expected start ping to be triggered")
	}
	if !endHit {
		t.Error("expected end ping to be triggered")
	}

	// Check that we logged successful completion
	logOutput := logBuf.String()
	if !strings.Contains(logOutput, "Backup completed successfully") {
		t.Errorf("expected log output to contain success confirmation, got:\n%s", logOutput)
	}
}

func TestApp_Run_Failure(t *testing.T) {
	// Start a mock telemetry server
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	// Generate a mock config that triggers failure (e.g. a missing block or we configure job type that errors)
	cfg := &config.Config{
		App: config.AppConfig{
			MachineName: "TestRunnerHost",
			LogLevel:    "info",
		},
		Telemetry: config.TelemetryConfig{
			PingStartURL:     ts.URL + "/ping/start",
			PingEndURL:       ts.URL + "/ping/end",
			PingAppendStatus: true,
			JournalUploadURL: ts.URL + "/upload",
		},
		Notifications: config.NotificationsConfig{
			Debug: &config.DebugConfig{
				Enabled: true,
			},
		},
		Jobs: []config.JobConfig{
			{
				Name: "tar_job",
				Type: "tar_ssh",
				// Missing tar_ssh block entirely, which causes runner instantiation failure!
			},
		},
	}

	// Verify that NewApp returns error due to validation
	mockClock := clock.NewMockClock(time.Now())
	_, err := NewApp(cfg, &bytes.Buffer{}, mockClock)
	if err == nil {
		t.Fatal("expected NewApp to return error when tar_ssh job lacks config block")
	}
	if !strings.Contains(err.Error(), "missing tar_ssh configuration block") {
		t.Errorf("expected config error, got %v", err)
	}
}
