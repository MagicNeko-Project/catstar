package notify

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"mime/multipart"
	"net/http"
	"sync"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

const defaultNotificationTimeout = 10 * time.Second

// HTTPDoer abstracts HTTP client transport for testing.
type HTTPDoer interface {
	Do(request *http.Request) (*http.Response, error)
}

// Notifier defines the interface for sending notifications.
type Notifier interface {
	Send(ctx context.Context, message string) error
	SendSummary(ctx context.Context, message string) error
	Name() string
}

// CompositeNotifier dispatches messages to multiple notifiers concurrently.
type CompositeNotifier struct {
	notifiers []Notifier
	logger    *slog.Logger
}

// NewCompositeNotifier builds a composite notifier based on configuration.
func NewCompositeNotifier(configuration *config.Config, logger *slog.Logger, httpClient HTTPDoer) *CompositeNotifier {
	var notifiers []Notifier

	if configuration.Notifications.Telegram != nil {
		notifiers = append(notifiers, &TelegramNotifier{
			Token:       configuration.Notifications.Telegram.BotToken,
			ChatID:      configuration.Notifications.Telegram.ChatID,
			SkipSummary: configuration.Notifications.Telegram.SkipSummary,
			client:      httpClient,
		})
	}

	if configuration.Notifications.Discord != nil {
		notifiers = append(notifiers, &DiscordNotifier{
			WebhookURL:  configuration.Notifications.Discord.WebhookURL,
			Username:    configuration.Notifications.Discord.Username,
			SkipSummary: configuration.Notifications.Discord.SkipSummary,
			client:      httpClient,
		})
	}

	if configuration.Notifications.Debug != nil && configuration.Notifications.Debug.Enabled {
		notifiers = append(notifiers, &DebugNotifier{
			SkipSummary: configuration.Notifications.Debug.SkipSummary,
			logger:      logger,
		})
	}

	return &CompositeNotifier{
		notifiers: notifiers,
		logger:    logger,
	}
}

// Send dispatches a message concurrently to all registered notifiers.
func (composite *CompositeNotifier) Send(ctx context.Context, message string) {
	if len(composite.notifiers) == 0 {
		return
	}

	var waitGroup sync.WaitGroup
	for _, registeredNotifier := range composite.notifiers {
		waitGroup.Add(1)
		go func(notifier Notifier) {
			defer waitGroup.Done()

			timeoutContext, cancelTimeout := context.WithTimeout(ctx, defaultNotificationTimeout)
			defer cancelTimeout()

			if err := notifier.Send(timeoutContext, message); err != nil {
				composite.logger.Error("Failed to dispatch notification",
					"notifier", notifier.Name(),
					"error", err,
				)
			}
		}(registeredNotifier)
	}
	waitGroup.Wait()
}

// SendSummary dispatches a summary message, respecting individual skip flags.
func (composite *CompositeNotifier) SendSummary(ctx context.Context, message string) {
	if len(composite.notifiers) == 0 {
		return
	}

	var waitGroup sync.WaitGroup
	for _, registeredNotifier := range composite.notifiers {
		waitGroup.Add(1)
		go func(notifier Notifier) {
			defer waitGroup.Done()

			timeoutContext, cancelTimeout := context.WithTimeout(ctx, defaultNotificationTimeout)
			defer cancelTimeout()

			if err := notifier.SendSummary(timeoutContext, message); err != nil {
				composite.logger.Error("Failed to dispatch summary notification",
					"notifier", notifier.Name(),
					"error", err,
				)
			}
		}(registeredNotifier)
	}
	waitGroup.Wait()
}

// --- Telegram Notifier ---

type TelegramNotifier struct {
	Token       string
	ChatID      string
	SkipSummary bool
	BaseURL     string
	client      HTTPDoer
}

func (telegram *TelegramNotifier) Name() string { return "telegram" }

func (telegram *TelegramNotifier) Send(ctx context.Context, message string) error {
	endpointURL := telegram.BaseURL
	if endpointURL == "" {
		endpointURL = fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", telegram.Token)
	}

	var payloadBuffer bytes.Buffer
	multipartWriter := multipart.NewWriter(&payloadBuffer)
	_ = multipartWriter.WriteField("chat_id", telegram.ChatID)
	_ = multipartWriter.WriteField("text", message)
	_ = multipartWriter.Close()

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpointURL, &payloadBuffer)
	if err != nil {
		return fmt.Errorf("failed to create telegram request: %w", err)
	}
	request.Header.Set("Content-Type", multipartWriter.FormDataContentType())

	response, err := telegram.client.Do(request)
	if err != nil {
		return fmt.Errorf("failed to dispatch telegram notification: %w", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)

	if response.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("telegram API returned status code: %d", response.StatusCode)
	}
	return nil
}

func (telegram *TelegramNotifier) SendSummary(ctx context.Context, message string) error {
	if telegram.SkipSummary {
		return nil
	}
	return telegram.Send(ctx, message)
}

// --- Discord Notifier ---

type DiscordNotifier struct {
	WebhookURL  string
	Username    string
	SkipSummary bool
	client      HTTPDoer
}

func (discord *DiscordNotifier) Name() string { return "discord" }

func (discord *DiscordNotifier) Send(ctx context.Context, message string) error {
	var payloadBuffer bytes.Buffer
	multipartWriter := multipart.NewWriter(&payloadBuffer)
	_ = multipartWriter.WriteField("username", discord.Username)
	_ = multipartWriter.WriteField("content", message)
	_ = multipartWriter.Close()

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, discord.WebhookURL, &payloadBuffer)
	if err != nil {
		return fmt.Errorf("failed to create discord request: %w", err)
	}
	request.Header.Set("Content-Type", multipartWriter.FormDataContentType())

	response, err := discord.client.Do(request)
	if err != nil {
		return fmt.Errorf("failed to dispatch discord notification: %w", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)

	if response.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("discord API returned status code: %d", response.StatusCode)
	}
	return nil
}

func (discord *DiscordNotifier) SendSummary(ctx context.Context, message string) error {
	if discord.SkipSummary {
		return nil
	}
	return discord.Send(ctx, message)
}

// --- Debug Notifier ---

type DebugNotifier struct {
	SkipSummary bool
	logger      *slog.Logger
}

func (debug *DebugNotifier) Name() string { return "debug" }

func (debug *DebugNotifier) Send(ctx context.Context, message string) error {
	debug.logger.Debug("Debug Notification", "message", message)
	return nil
}

func (debug *DebugNotifier) SendSummary(ctx context.Context, message string) error {
	if debug.SkipSummary {
		return nil
	}
	return debug.Send(ctx, message)
}
