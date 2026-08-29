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
	var startPingReceived, endPingReceived bool
	var telemetryMutex sync.Mutex

	mockServer := httptest.NewServer(http.HandlerFunc(func(responseWriter http.ResponseWriter, request *http.Request) {
		telemetryMutex.Lock()
		defer telemetryMutex.Unlock()
		switch request.URL.Path {
		case "/ping/start":
			startPingReceived = true
			responseWriter.WriteHeader(http.StatusOK)
		case "/ping/end/0":
			endPingReceived = true
			responseWriter.WriteHeader(http.StatusOK)
		case "/upload":
			responseWriter.WriteHeader(http.StatusOK)
			_, _ = responseWriter.Write([]byte("https://paste.example.com/success"))
		default:
			responseWriter.WriteHeader(http.StatusNotFound)
		}
	}))
	defer mockServer.Close()

	testConfig := &config.Config{
		App: config.AppConfig{
			MachineName: "TestRunnerHost",
			LogLevel:    "info",
		},
		Telemetry: config.TelemetryConfig{
			PingStartURL:     mockServer.URL + "/ping/start",
			PingEndURL:       mockServer.URL + "/ping/end",
			PingAppendStatus: true,
			JournalUploadURL: mockServer.URL + "/upload",
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

	startTime := time.Date(2026, 5, 21, 10, 0, 0, 0, time.UTC)
	mockClock := clock.NewMockClock(startTime)

	var logBuffer bytes.Buffer
	appInstance, err := NewApp(testConfig, &logBuffer, mockClock)
	if err != nil {
		t.Fatalf("failed to initialize App: %v", err)
	}

	ctx := context.Background()
	exitCode := appInstance.Run(ctx)

	if exitCode != 0 {
		t.Fatalf("expected exit code 0, got %d. Logs:\n%s", exitCode, logBuffer.String())
	}

	telemetryMutex.Lock()
	defer telemetryMutex.Unlock()

	if !startPingReceived {
		t.Error("expected start ping to be triggered")
	}
	if !endPingReceived {
		t.Error("expected end ping to be triggered")
	}

	logOutput := logBuffer.String()
	if !strings.Contains(logOutput, "Backup completed successfully") {
		t.Errorf("expected log output to contain success confirmation, got:\n%s", logOutput)
	}
}

func TestApp_Run_Failure(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(responseWriter http.ResponseWriter, _ *http.Request) {
		responseWriter.WriteHeader(http.StatusOK)
	}))
	defer mockServer.Close()

	testConfig := &config.Config{
		App: config.AppConfig{
			MachineName: "TestRunnerHost",
			LogLevel:    "info",
		},
		Telemetry: config.TelemetryConfig{
			PingStartURL:     mockServer.URL + "/ping/start",
			PingEndURL:       mockServer.URL + "/ping/end",
			PingAppendStatus: true,
			JournalUploadURL: mockServer.URL + "/upload",
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
			},
		},
	}

	mockClock := clock.NewMockClock(time.Now())
	_, err := NewApp(testConfig, &bytes.Buffer{}, mockClock)
	if err == nil {
		t.Fatal("expected NewApp to return error when tar_ssh job lacks config block")
	}
	if !strings.Contains(err.Error(), "missing tar_ssh configuration block") {
		t.Errorf("expected config error, got %v", err)
	}
}
