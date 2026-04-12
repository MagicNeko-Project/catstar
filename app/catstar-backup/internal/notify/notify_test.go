package notify

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

type MockNotifier struct {
	name          string
	mu            sync.Mutex
	sentMessages  []string
	sentSummaries []string
	delay         time.Duration
}

func (m *MockNotifier) Name() string { return m.name }

func (m *MockNotifier) Send(ctx context.Context, msg string) error {
	if m.delay > 0 {
		time.Sleep(m.delay)
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sentMessages = append(m.sentMessages, msg)
	return nil
}

func (m *MockNotifier) SendSummary(ctx context.Context, msg string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sentSummaries = append(m.sentSummaries, msg)
	return nil
}

func TestCompositeNotifier_FanOut(t *testing.T) {
	mockA := &MockNotifier{name: "MockA"}
	mockB := &MockNotifier{name: "MockB"}

	// Create logger that discards output
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	comp := &CompositeNotifier{
		notifiers: []Notifier{mockA, mockB},
		logger:    logger,
	}

	ctx := context.Background()
	comp.Send(ctx, "hello world")

	// Since Send is asynchronous under the hood but blocked by WaitGroup,
	// when it returns, all children should have completed.

	if len(mockA.sentMessages) != 1 || mockA.sentMessages[0] != "hello world" {
		t.Fatalf("MockA did not receive expected message")
	}
	if len(mockB.sentMessages) != 1 || mockB.sentMessages[0] != "hello world" {
		t.Fatalf("MockB did not receive expected message")
	}

	comp.SendSummary(ctx, "summary string")

	if len(mockA.sentSummaries) != 1 || mockA.sentSummaries[0] != "summary string" {
		t.Fatalf("MockA did not receive expected summary")
	}
}

func TestTelegramNotifier_Integration(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/botTEST_TOKEN/sendMessage" {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ts.Close()

	// Test the valid mock server connection
	tn := &TelegramNotifier{
		Token:   "TEST_TOKEN",
		ChatID:  "123",
		BaseURL: ts.URL + "/botTEST_TOKEN/sendMessage",
		client:  ts.Client(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	if err := tn.Send(ctx, "test"); err != nil {
		t.Fatalf("expected successful send to mock server, got error: %v", err)
	}

	// Test invalid routing (404 Not Found)
	tnBad := &TelegramNotifier{
		Token:   "BAD_TOKEN",
		ChatID:  "123",
		BaseURL: ts.URL + "/bad_path",
		client:  ts.Client(),
	}

	if err := tnBad.Send(ctx, "test"); err == nil {
		t.Fatalf("expected error from 404 response, got nil")
	}
}

func TestNewCompositeNotifier_Builder(t *testing.T) {
	cfg := &config.Config{
		Notifications: config.NotificationsConfig{
			Telegram: &config.TelegramConfig{
				BotToken: "test",
			},
			Discord: &config.DiscordConfig{
				WebhookURL: "http://test",
			},
			Debug: &config.DebugConfig{
				Enabled: true,
			},
		},
	}

	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	dummyHTTP := &http.Client{} // Safe to use real empty client struct here as it's not actually invoked
	comp := NewCompositeNotifier(cfg, logger, dummyHTTP)

	if len(comp.notifiers) != 3 {
		t.Fatalf("expected 3 notifiers based on config, got %d", len(comp.notifiers))
	}
}
