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

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

// LogBuffer is a thread-safe in-memory buffer that captures log output.
type LogBuffer struct {
	mutex  sync.Mutex
	buffer bytes.Buffer
}

func NewLogBuffer() *LogBuffer {
	return &LogBuffer{}
}

func (logBuffer *LogBuffer) Write(payload []byte) (int, error) {
	logBuffer.mutex.Lock()
	defer logBuffer.mutex.Unlock()
	return logBuffer.buffer.Write(payload)
}

func (logBuffer *LogBuffer) String() string {
	logBuffer.mutex.Lock()
	defer logBuffer.mutex.Unlock()
	return logBuffer.buffer.String()
}

// HTTPDoer abstracts HTTP client transport for testing.
type HTTPDoer interface {
	Do(request *http.Request) (*http.Response, error)
}

// TelemetryClient handles start/stop HTTP pings and log uploads.
type TelemetryClient struct {
	config     *config.Config
	httpClient HTTPDoer
}

func NewTelemetryClient(configuration *config.Config, httpClient HTTPDoer) *TelemetryClient {
	return &TelemetryClient{
		config:     configuration,
		httpClient: httpClient,
	}
}

// PingStart sends the initialization telemetry payload.
func (telemetry *TelemetryClient) PingStart(ctx context.Context, message string) error {
	if telemetry.config.Telemetry.PingStartURL == "" {
		return nil
	}

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, telemetry.config.Telemetry.PingStartURL, strings.NewReader(message))
	if err != nil {
		return fmt.Errorf("failed to create start ping request: %w", err)
	}
	request.Header.Set("Content-Type", "text/plain")

	response, err := telemetry.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("failed to execute start ping: %w", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)

	if response.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("ping start failed with status code: %d", response.StatusCode)
	}
	return nil
}

// PingEnd sends the completion telemetry payload.
func (telemetry *TelemetryClient) PingEnd(ctx context.Context, statusCode int, logText string) error {
	if telemetry.config.Telemetry.PingEndURL == "" {
		return nil
	}

	endpointURL := telemetry.config.Telemetry.PingEndURL
	if telemetry.config.Telemetry.PingAppendStatus {
		endpointURL = fmt.Sprintf("%s/%d", endpointURL, statusCode)
	}

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpointURL, strings.NewReader(logText))
	if err != nil {
		return fmt.Errorf("failed to create end ping request: %w", err)
	}
	request.Header.Set("Content-Type", "text/plain")

	response, err := telemetry.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("failed to execute end ping: %w", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)

	if response.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("ping end failed with status code: %d", response.StatusCode)
	}
	return nil
}

// UploadLogs uploads captured logs to a remote journal or paste endpoint.
func (telemetry *TelemetryClient) UploadLogs(ctx context.Context, logText string) string {
	if telemetry.config.Telemetry.JournalUploadURL == "" {
		return logText
	}

	var payloadBuffer bytes.Buffer
	multipartWriter := multipart.NewWriter(&payloadBuffer)

	formFileWriter, err := multipartWriter.CreateFormFile("logs", "backup.log")
	if err != nil {
		return logText
	}
	if _, err := io.Copy(formFileWriter, strings.NewReader(logText)); err != nil {
		return logText
	}
	_ = multipartWriter.Close()

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, telemetry.config.Telemetry.JournalUploadURL, &payloadBuffer)
	if err != nil {
		return logText
	}
	request.Header.Set("Content-Type", multipartWriter.FormDataContentType())

	response, err := telemetry.httpClient.Do(request)
	if err != nil {
		return logText
	}
	defer response.Body.Close()

	if response.StatusCode >= http.StatusBadRequest {
		_, _ = io.Copy(io.Discard, response.Body)
		return logText
	}

	bodyBytes, err := io.ReadAll(response.Body)
	if err != nil {
		return logText
	}

	return fmt.Sprintf("日志：%s", strings.TrimSpace(string(bodyBytes)))
}
