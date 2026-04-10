package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// AppConfig represents the strictly typed configuration for the Catstar backup runner.
type AppConfig struct {
	MachineName string

	// Restic Engine Configurations
	ResticRoot       string
	ResticRepository string
	ResticPassword   string
	ResticPackSize   string
	ResticCacheDir   string

	// Tar/SSH Engine Configurations
	TarSSHServer       string
	TarOpenSSLType     string
	TarOpenSSLPassword string
	TarFileName        string

	// BTRFS Engine Configurations
	BtrfsSnapshotsRoot string
	BtrfsSnapshots     map[string]string // Dynamically populated from BTRFS_SNAPSHOT_*

	// Notification and Monitoring
	TelegramBotToken        string
	TelegramSendMsgUser     string
	TelegramSkipSummary     bool
	DiscordWebhookURL       string
	DiscordUsername         string
	DiscordSkipSummary      bool
	DebugSkipSummary        bool
	NotifyDebug             bool
	NotifySendSummary       bool
	NotifySendSummaryHours  []int
	NotifySendVerbose       bool

	// Healthcheck Ping Config
	HTTPPingURL           string
	HTTPPingAppendStatus  bool
	HTTPPingStartURL      string
	JournalUploadURL      string

	// Flags
	BackupTest bool
	TimeZone   string
}

// Load reads environment variables and parses them into the strongly typed AppConfig.
// It returns an error if essential configuration validation fails.
func Load() (*AppConfig, error) {
	cfg := &AppConfig{
		MachineName:             getEnv("MACHINE_NAME", "Catstar-Node"),
		ResticRoot:              getEnv("RESTIC_ROOT", ""),
		ResticRepository:        getEnv("RESTIC_REPOSITORY", ""),
		ResticPassword:          getEnv("RESTIC_PASSWORD", ""),
		ResticPackSize:          getEnv("RESTIC_PACK_SIZE", "64"),
		ResticCacheDir:          getEnv("RESTIC_CACHE_DIR", "/tmp/restic-cache"),
		TarSSHServer:            getEnv("TAR_SSH_SERVER", ""),
		TarOpenSSLType:          getEnv("TAR_OPENSSL_TYPE", "aes-128-cbc"),
		TarOpenSSLPassword:      getEnv("TAR_OPENSSL_PASSWORD", ""),
		TarFileName:             getEnv("TAR_FILE_NAME", "/data/backup-%(%F_%H%M%S)T.tar.zstd.aes-128-cbc"),
		BtrfsSnapshotsRoot:      getEnv("BTRFS_SNAPSHOTS_ROOT", ""),
		BtrfsSnapshots:          make(map[string]string),
		TelegramBotToken:        getEnv("TELEGRAM_BOT_TOKEN", ""),
		TelegramSendMsgUser:     getEnv("TELEGRAM_BOT_SendMsg_User", ""),
		TelegramSkipSummary:     getEnvBool("TELEGRAM_SKIP_SUMMARY", true),
		DiscordWebhookURL:       getEnv("DISCORD_WEBHOOK_URL", ""),
		DiscordUsername:         getEnv("DISCORD_USERNAME", "Catstar Backup"),
		DiscordSkipSummary:      getEnvBool("DISCORD_SKIP_SUMMARY", true),
		DebugSkipSummary:        getEnvBool("DEBUG_SKIP_SUMMARY", false),
		NotifyDebug:             getEnvBool("NOTIFY_DEBUG", false),
		NotifySendSummary:       getEnvBool("NOTIFY_SEND_SUMMARY", true),
		NotifySendVerbose:       getEnvBool("NOTIFY_SEND_VERBOSE", false),
		HTTPPingURL:             getEnv("HTTP_PING_URL", ""),
		HTTPPingAppendStatus:    getEnvBool("HTTP_PING_APPEND_STATUS", true),
		HTTPPingStartURL:        getEnv("HTTP_PING_START_URL", ""),
		JournalUploadURL:        getEnv("JOURNAL_UPLOAD_URL", ""),
		BackupTest:              getEnvBool("BACKUP_TEST", false),
		TimeZone:                getEnv("TZ", "Asia/Shanghai"),
	}

	// Parse Summary Hours
	hoursStr := getEnv("NOTIFY_SEND_SUMMARY_HOURS", "")
	if hoursStr != "" {
		for _, h := range strings.Fields(hoursStr) {
			if parsedHour, err := strconv.Atoi(h); err == nil {
				cfg.NotifySendSummaryHours = append(cfg.NotifySendSummaryHours, parsedHour)
			}
		}
	}

	// Parse Dynamic BTRFS Snapshots
	for _, env := range os.Environ() {
		parts := strings.SplitN(env, "=", 2)
		if len(parts) == 2 && strings.HasPrefix(parts[0], "BTRFS_SNAPSHOT_") {
			dest := strings.TrimPrefix(parts[0], "BTRFS_SNAPSHOT_")
			cfg.BtrfsSnapshots[dest] = parts[1]
		}
	}

	if err := validate(cfg); err != nil {
		return nil, err
	}

	// Set timezone globally if specified
	if loc, err := time.LoadLocation(cfg.TimeZone); err == nil {
		time.Local = loc
	}

	return cfg, nil
}

func validate(cfg *AppConfig) error {
	// Basic validation to fail-fast
	if cfg.TelegramBotToken != "" && cfg.TelegramSendMsgUser == "" {
		return fmt.Errorf("TELEGRAM_BOT_SendMsg_User is required when TELEGRAM_BOT_TOKEN is set")
	}
	return nil
}

func getEnv(key, fallback string) string {
	if val, ok := os.LookupEnv(key); ok {
		return val
	}
	return fallback
}

func getEnvBool(key string, fallback bool) bool {
	if val, ok := os.LookupEnv(key); ok {
		b, err := strconv.ParseBool(val)
		if err == nil {
			return b
		}
		// Also handle common bash truthy strings
		v := strings.ToLower(strings.TrimSpace(val))
		if v == "1" || v == "true" || v == "yes" {
			return true
		}
		if v == "0" || v == "false" || v == "no" {
			return false
		}
	}
	return fallback
}
