package notify

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

type MockNotifier struct {
	name          string
	mutex         sync.Mutex
	sentMessages  []string
	sentSummaries []string
}

func (mock *MockNotifier) Name() string { return mock.name }

func (mock *MockNotifier) Send(ctx context.Context, message string) error {
	mock.mutex.Lock()
	defer mock.mutex.Unlock()
	mock.sentMessages = append(mock.sentMessages, message)
	return nil
}

func (mock *MockNotifier) SendSummary(ctx context.Context, message string) error {
	mock.mutex.Lock()
	defer mock.mutex.Unlock()
	mock.sentSummaries = append(mock.sentSummaries, message)
	return nil
}

func TestCompositeNotifier_FanOut(t *testing.T) {
	mockNotifierA := &MockNotifier{name: "MockA"}
	mockNotifierB := &MockNotifier{name: "MockB"}

	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))

	composite := &CompositeNotifier{
		notifiers: []Notifier{mockNotifierA, mockNotifierB},
		logger:    discardLogger,
	}

	ctx := context.Background()
	composite.Send(ctx, "hello world")

	if len(mockNotifierA.sentMessages) != 1 || mockNotifierA.sentMessages[0] != "hello world" {
		t.Fatalf("MockA did not receive expected message")
	}
	if len(mockNotifierB.sentMessages) != 1 || mockNotifierB.sentMessages[0] != "hello world" {
		t.Fatalf("MockB did not receive expected message")
	}

	composite.SendSummary(ctx, "summary string")

	if len(mockNotifierA.sentSummaries) != 1 || mockNotifierA.sentSummaries[0] != "summary string" {
		t.Fatalf("MockA did not receive expected summary")
	}
}

func TestTelegramNotifier_Integration(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(responseWriter http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/botTEST_TOKEN/sendMessage" {
			responseWriter.WriteHeader(http.StatusOK)
			return
		}
		responseWriter.WriteHeader(http.StatusNotFound)
	}))
	defer mockServer.Close()

	telegramNotifier := &TelegramNotifier{
		Token:   "TEST_TOKEN",
		ChatID:  "123",
		BaseURL: mockServer.URL + "/botTEST_TOKEN/sendMessage",
		client:  mockServer.Client(),
	}

	ctx, cancelTimeout := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancelTimeout()

	if err := telegramNotifier.Send(ctx, "test"); err != nil {
		t.Fatalf("expected successful send to mock server, got error: %v", err)
	}

	badTelegramNotifier := &TelegramNotifier{
		Token:   "BAD_TOKEN",
		ChatID:  "123",
		BaseURL: mockServer.URL + "/bad_path",
		client:  mockServer.Client(),
	}

	if err := badTelegramNotifier.Send(ctx, "test"); err == nil {
		t.Fatalf("expected error from 404 response, got nil")
	}
}

func TestDiscordNotifier_Integration(t *testing.T) {
	mockServer := httptest.NewServer(http.HandlerFunc(func(responseWriter http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/webhook" {
			responseWriter.WriteHeader(http.StatusOK)
			return
		}
		responseWriter.WriteHeader(http.StatusNotFound)
	}))
	defer mockServer.Close()

	discordNotifier := &DiscordNotifier{
		WebhookURL: mockServer.URL + "/webhook",
		Username:   "backup-bot",
		client:     mockServer.Client(),
	}

	ctx := context.Background()
	if err := discordNotifier.Send(ctx, "test message"); err != nil {
		t.Fatalf("expected successful discord message dispatch, got error: %v", err)
	}

	if err := discordNotifier.SendSummary(ctx, "test summary"); err != nil {
		t.Fatalf("expected successful discord summary dispatch, got error: %v", err)
	}

	discordNotifierSkip := &DiscordNotifier{
		WebhookURL:  mockServer.URL + "/webhook",
		Username:    "backup-bot",
		SkipSummary: true,
		client:      mockServer.Client(),
	}
	if err := discordNotifierSkip.SendSummary(ctx, "test summary"); err != nil {
		t.Fatalf("expected skipped summary to return nil error, got: %v", err)
	}
}

func TestDebugNotifier(t *testing.T) {
	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	debugNotifier := &DebugNotifier{
		logger: discardLogger,
	}

	ctx := context.Background()
	if err := debugNotifier.Send(ctx, "debug test"); err != nil {
		t.Fatalf("expected debug notifier send to succeed, got: %v", err)
	}
	if err := debugNotifier.SendSummary(ctx, "debug summary"); err != nil {
		t.Fatalf("expected debug notifier summary to succeed, got: %v", err)
	}

	debugNotifierSkip := &DebugNotifier{
		SkipSummary: true,
		logger:      discardLogger,
	}
	if err := debugNotifierSkip.SendSummary(ctx, "debug summary"); err != nil {
		t.Fatalf("expected skipped debug summary to return nil, got: %v", err)
	}
}

func TestNewCompositeNotifier_Builder(t *testing.T) {
	testConfig := &config.Config{
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

	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	dummyHTTP := &http.Client{}
	composite := NewCompositeNotifier(testConfig, discardLogger, dummyHTTP)

	if len(composite.notifiers) != 3 {
		t.Fatalf("expected 3 notifiers based on config, got %d", len(composite.notifiers))
	}
}
