package observability

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

func TestLogBuffer(t *testing.T) {
	buf := NewLogBuffer()

	// Test writing
	n, err := buf.Write([]byte("test log"))
	if err != nil {
		t.Fatalf("unexpected error writing to buffer: %v", err)
	}
	if n != 8 {
		t.Fatalf("expected to write 8 bytes, wrote %d", n)
	}

	// Test concurrent access (this shouldn't panic/race if mu.Lock() is working)
	for i := 0; i < 100; i++ {
		go func(val int) {
			_, _ = buf.Write([]byte(fmt.Sprintf("%d", val)))
		}(i)
	}

	// Ensure string method works
	str := buf.String()
	if str == "" {
		t.Fatalf("buffer string is unexpectedly empty")
	}
}

func TestTelemetryClient_Ping(t *testing.T) {
	// Create a mock HTTP server to intercept pings
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/start" {
			w.WriteHeader(http.StatusOK)
			return
		}
		if r.URL.Path == "/end/0" {
			w.WriteHeader(http.StatusOK)
			return
		}
		if r.URL.Path == "/upload" {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("https://pastebin.example.com/xyz123"))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ts.Close()

	cfg := &config.Config{
		Telemetry: config.TelemetryConfig{
			PingStartURL:     ts.URL + "/start",
			PingEndURL:       ts.URL + "/end",
			PingAppendStatus: true,
			JournalUploadURL: ts.URL + "/upload",
		},
	}

	client := NewTelemetryClient(cfg)
	ctx := context.Background()

	t.Run("PingStart Success", func(t *testing.T) {
		if err := client.PingStart(ctx, "started"); err != nil {
			t.Fatalf("expected no error on start ping, got %v", err)
		}
	})

	t.Run("PingEnd Success", func(t *testing.T) {
		if err := client.PingEnd(ctx, 0, "logs"); err != nil {
			t.Fatalf("expected no error on end ping, got %v", err)
		}
	})

	t.Run("PingEnd Failure Simulation", func(t *testing.T) {
		if err := client.PingEnd(ctx, 1, "logs"); err == nil {
			t.Fatalf("expected 404 error on bad end ping path (/end/1), got nil")
		}
	})

	t.Run("UploadLogs Success", func(t *testing.T) {
		url := client.UploadLogs(ctx, "log content")
		expected := "日志：https://pastebin.example.com/xyz123"
		if url != expected {
			t.Fatalf("expected URL %q, got %q", expected, url)
		}
	})
}
