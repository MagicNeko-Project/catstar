package observability

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

// LogBuffer is a thread-safe buffer that captures log output during the run
// for upload later if an error occurs or a summary is requested.
type LogBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func NewLogBuffer() *LogBuffer {
	return &LogBuffer{}
}

func (l *LogBuffer) Write(p []byte) (n int, err error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.buf.Write(p)
}

func (l *LogBuffer) String() string {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.buf.String()
}

// TelemetryClient handles start/stop HTTP pings and log uploads.
type TelemetryClient struct {
	cfg    *config.Config
	client *http.Client
}

func NewTelemetryClient(cfg *config.Config) *TelemetryClient {
	return &TelemetryClient{
		cfg: cfg,
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

// PingStart sends the initialization payload.
func (t *TelemetryClient) PingStart(ctx context.Context, message string) error {
	if t.cfg.Telemetry.PingStartURL == "" {
		return nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.cfg.Telemetry.PingStartURL, strings.NewReader(message))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "text/plain")

	resp, err := t.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("ping start failed with status: %d", resp.StatusCode)
	}
	return nil
}

// PingEnd sends the final state payload, appending the status code if configured.
func (t *TelemetryClient) PingEnd(ctx context.Context, statusCode int, logText string) error {
	if t.cfg.Telemetry.PingEndURL == "" {
		return nil
	}

	url := t.cfg.Telemetry.PingEndURL
	if t.cfg.Telemetry.PingAppendStatus {
		url = fmt.Sprintf("%s/%d", url, statusCode)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(logText))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "text/plain")

	resp, err := t.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("ping end failed with status: %d", resp.StatusCode)
	}
	return nil
}

// UploadLogs uploads the captured logs to a pastebin-like service (e.g., ix.io).
// It returns the URL of the uploaded logs or the raw logs if upload fails/is unconfigured.
func (t *TelemetryClient) UploadLogs(ctx context.Context, logText string) string {
	if t.cfg.Telemetry.JournalUploadURL == "" {
		return logText // Fallback to returning raw text if no URL configured
	}

	var b bytes.Buffer
	w := multipart.NewWriter(&b)
	
	// Create a form file field named "logs"
	fw, err := w.CreateFormFile("logs", "backup.log")
	if err != nil {
		return logText
	}
	if _, err := io.Copy(fw, strings.NewReader(logText)); err != nil {
		return logText
	}
	w.Close()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.cfg.Telemetry.JournalUploadURL, &b)
	if err != nil {
		return logText
	}
	req.Header.Set("Content-Type", w.FormDataContentType())

	resp, err := t.client.Do(req)
	if err != nil {
		return logText
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return logText
	}

	// Assuming the service returns the URL in the response body
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return logText
	}

	return fmt.Sprintf("日志：%s", strings.TrimSpace(string(bodyBytes)))
}
