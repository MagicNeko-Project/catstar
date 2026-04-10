package notify

import (
	"bytes"
	"context"
	"fmt"
	"log/slog"
	"mime/multipart"
	"net/http"
	"sync"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
)

// Notifier defines the interface for sending backup notifications.
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

// NewCompositeNotifier builds a notifier based on the configuration.
func NewCompositeNotifier(cfg *config.AppConfig, logger *slog.Logger) *CompositeNotifier {
	var notifiers []Notifier

	if cfg.TelegramBotToken != "" {
		notifiers = append(notifiers, &TelegramNotifier{
			Token:       cfg.TelegramBotToken,
			ChatID:      cfg.TelegramSendMsgUser,
			SkipSummary: cfg.TelegramSkipSummary,
		})
	}

	if cfg.DiscordWebhookURL != "" {
		notifiers = append(notifiers, &DiscordNotifier{
			WebhookURL:  cfg.DiscordWebhookURL,
			Username:    cfg.DiscordUsername,
			SkipSummary: cfg.DiscordSkipSummary,
		})
	}

	if cfg.NotifyDebug {
		notifiers = append(notifiers, &DebugNotifier{
			SkipSummary: cfg.DebugSkipSummary,
			logger:      logger,
		})
	}

	return &CompositeNotifier{
		notifiers: notifiers,
		logger:    logger,
	}
}

// Send dispatches the message concurrently to all registered notifiers.
func (c *CompositeNotifier) Send(ctx context.Context, message string) {
	if len(c.notifiers) == 0 {
		return
	}

	var wg sync.WaitGroup
	for _, n := range c.notifiers {
		wg.Add(1)
		go func(notifier Notifier) {
			defer wg.Done()
			
			// Give each network call a reasonable timeout
			timeoutCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
			defer cancel()

			if err := notifier.Send(timeoutCtx, message); err != nil {
				c.logger.Error("Failed to dispatch notification",
					"notifier", notifier.Name(),
					"error", err,
				)
			}
		}(n)
	}
	wg.Wait()
}

// SendSummary dispatches the summary message, respecting individual skip flags.
func (c *CompositeNotifier) SendSummary(ctx context.Context, message string) {
	if len(c.notifiers) == 0 {
		return
	}

	var wg sync.WaitGroup
	for _, n := range c.notifiers {
		wg.Add(1)
		go func(notifier Notifier) {
			defer wg.Done()
			
			timeoutCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
			defer cancel()

			if err := notifier.SendSummary(timeoutCtx, message); err != nil {
				c.logger.Error("Failed to dispatch summary notification",
					"notifier", notifier.Name(),
					"error", err,
				)
			}
		}(n)
	}
	wg.Wait()
}

// --- Implementations ---

type TelegramNotifier struct {
	Token       string
	ChatID      string
	SkipSummary bool
}

func (t *TelegramNotifier) Name() string { return "telegram" }

func (t *TelegramNotifier) Send(ctx context.Context, message string) error {
	url := fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", t.Token)

	var b bytes.Buffer
	w := multipart.NewWriter(&b)
	_ = w.WriteField("chat_id", t.ChatID)
	_ = w.WriteField("text", message)
	w.Close()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, &b)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("telegram API returned status: %d", resp.StatusCode)
	}
	return nil
}

func (t *TelegramNotifier) SendSummary(ctx context.Context, message string) error {
	if t.SkipSummary {
		return nil
	}
	return t.Send(ctx, message)
}

type DiscordNotifier struct {
	WebhookURL  string
	Username    string
	SkipSummary bool
}

func (d *DiscordNotifier) Name() string { return "discord" }

func (d *DiscordNotifier) Send(ctx context.Context, message string) error {
	var b bytes.Buffer
	w := multipart.NewWriter(&b)
	_ = w.WriteField("username", d.Username)
	_ = w.WriteField("content", message)
	w.Close()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, d.WebhookURL, &b)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("discord API returned status: %d", resp.StatusCode)
	}
	return nil
}

func (d *DiscordNotifier) SendSummary(ctx context.Context, message string) error {
	if d.SkipSummary {
		return nil
	}
	return d.Send(ctx, message)
}

type DebugNotifier struct {
	SkipSummary bool
	logger      *slog.Logger
}

func (d *DebugNotifier) Name() string { return "debug" }

func (d *DebugNotifier) Send(ctx context.Context, message string) error {
	d.logger.Debug("Debug Notification", "message", message)
	return nil
}

func (d *DebugNotifier) SendSummary(ctx context.Context, message string) error {
	if d.SkipSummary {
		return nil
	}
	return d.Send(ctx, message)
}
