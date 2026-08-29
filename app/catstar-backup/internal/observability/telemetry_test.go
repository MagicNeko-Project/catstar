package observability

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

func TestLogBuffer(t *testing.T) {
	logBuffer := NewLogBuffer()

	bytesWritten, err := logBuffer.Write([]byte("test log"))
	if err != nil {
		t.Fatalf("unexpected error writing to buffer: %v", err)
	}
	if bytesWritten != 8 {
		t.Fatalf("expected to write 8 bytes, wrote %d", bytesWritten)
	}

	var waitGroup sync.WaitGroup
	for iterationIndex := 0; iterationIndex < 100; iterationIndex++ {
		waitGroup.Add(1)
		go func(value int) {
			defer waitGroup.Done()
			_, _ = logBuffer.Write([]byte(fmt.Sprintf("%d", value)))
		}(iterationIndex)
	}
	waitGroup.Wait()

	bufferString := logBuffer.String()
	if bufferString == "" {
		t.Fatalf("buffer string is unexpectedly empty")
	}
}

func TestTelemetryClient_Ping(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(responseWriter http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/start" {
			responseWriter.WriteHeader(http.StatusOK)
			return
		}
		if request.URL.Path == "/end/0" {
			responseWriter.WriteHeader(http.StatusOK)
			return
		}
		if request.URL.Path == "/upload" {
			responseWriter.WriteHeader(http.StatusOK)
			_, _ = responseWriter.Write([]byte("https://pastebin.example.com/xyz123"))
			return
		}
		responseWriter.WriteHeader(http.StatusNotFound)
	}))
	defer mockServer.Close()

	testConfig := &config.Config{
		Telemetry: config.TelemetryConfig{
			PingStartURL:     mockServer.URL + "/start",
			PingEndURL:       mockServer.URL + "/end",
			PingAppendStatus: true,
			JournalUploadURL: mockServer.URL + "/upload",
		},
	}

	telemetryClient := NewTelemetryClient(testConfig, mockServer.Client())
	ctx := context.Background()

	t.Run("PingStart Success", func(subtest *testing.T) {
		if err := telemetryClient.PingStart(ctx, "started"); err != nil {
			subtest.Fatalf("expected no error on start ping, got %v", err)
		}
	})

	t.Run("PingEnd Success", func(subtest *testing.T) {
		if err := telemetryClient.PingEnd(ctx, 0, "logs"); err != nil {
			subtest.Fatalf("expected no error on end ping, got %v", err)
		}
	})

	t.Run("PingEnd Failure Simulation", func(subtest *testing.T) {
		if err := telemetryClient.PingEnd(ctx, 1, "logs"); err == nil {
			subtest.Fatalf("expected 404 error on bad end ping path (/end/1), got nil")
		}
	})

	t.Run("UploadLogs Success", func(subtest *testing.T) {
		uploadedURL := telemetryClient.UploadLogs(ctx, "log content")
		expectedURL := "日志：https://pastebin.example.com/xyz123"
		if uploadedURL != expectedURL {
			subtest.Fatalf("expected URL %q, got %q", expectedURL, uploadedURL)
		}
	})
}
