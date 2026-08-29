package config

import (
	"fmt"
	"os"
	"time"

	"github.com/go-playground/validator/v10"
	"gopkg.in/yaml.v3"
)

type StrategyType string

const (
	StrategyTypeRestic      StrategyType = "restic"
	StrategyTypeBtrfsRestic StrategyType = "btrfs_restic"
	StrategyTypeTarSSH      StrategyType = "tar_ssh"
	StrategyTypeTest        StrategyType = "test"
)

// Config represents the root configuration structure for backup operations.
type Config struct {
	App           AppConfig           `yaml:"app" validate:"required"`
	Notifications NotificationsConfig `yaml:"notifications"`
	Telemetry     TelemetryConfig     `yaml:"telemetry"`
	Jobs          []JobConfig         `yaml:"jobs" validate:"dive"`
}

// AppConfig defines global application settings.
type AppConfig struct {
	MachineName string `yaml:"machine_name" validate:"required"`
	TimeZone    string `yaml:"timezone" validate:"required,timezone"`
	LogLevel    string `yaml:"log_level" validate:"omitempty,oneof=debug info warn error"`
}

// NotificationsConfig defines notification sinks and settings.
type NotificationsConfig struct {
	SendSummary  bool            `yaml:"send_summary"`
	SendVerbose  bool            `yaml:"send_verbose"`
	SummaryHours []int           `yaml:"summary_hours" validate:"omitempty,dive,min=0,max=23"`
	Telegram     *TelegramConfig `yaml:"telegram,omitempty"`
	Discord      *DiscordConfig  `yaml:"discord,omitempty"`
	Debug        *DebugConfig    `yaml:"debug,omitempty"`
}

type TelegramConfig struct {
	BotToken    string `yaml:"bot_token" validate:"required"`
	ChatID      string `yaml:"chat_id" validate:"required"`
	SkipSummary bool   `yaml:"skip_summary"`
}

type DiscordConfig struct {
	WebhookURL  string `yaml:"webhook_url" validate:"required,url"`
	Username    string `yaml:"username" validate:"required"`
	SkipSummary bool   `yaml:"skip_summary"`
}

type DebugConfig struct {
	Enabled     bool `yaml:"enabled"`
	SkipSummary bool `yaml:"skip_summary"`
}

// TelemetryConfig defines HTTP endpoints for status tracking and logging.
type TelemetryConfig struct {
	PingStartURL     string `yaml:"ping_start_url" validate:"omitempty,url"`
	PingEndURL       string `yaml:"ping_end_url" validate:"omitempty,url"`
	PingAppendStatus bool   `yaml:"ping_append_status"`
	JournalUploadURL string `yaml:"journal_upload_url" validate:"omitempty,url"`
}

// JobConfig represents a single backup strategy task.
type JobConfig struct {
	Name        string             `yaml:"name" validate:"required"`
	Type        string             `yaml:"type" validate:"required,oneof=restic btrfs_restic tar_ssh test"`
	Restic      *ResticConfig      `yaml:"restic,omitempty"`
	BtrfsRestic *BtrfsResticConfig `yaml:"btrfs_restic,omitempty"`
	TarSSH      *TarSSHConfig      `yaml:"tar_ssh,omitempty"`
}

type ResticConfig struct {
	Root       string `yaml:"root" validate:"required,dir"`
	Repository string `yaml:"repository" validate:"required"`
	Password   string `yaml:"password" validate:"required"`
	PackSize   string `yaml:"pack_size" validate:"omitempty,numeric"`
	CacheDir   string `yaml:"cache_dir" validate:"omitempty,dir"`
}

type BtrfsResticConfig struct {
	SnapshotsRoot string            `yaml:"snapshots_root" validate:"required,dir"`
	Repository    string            `yaml:"repository" validate:"required"`
	Password      string            `yaml:"password" validate:"required"`
	Subvolumes    map[string]string `yaml:"subvolumes" validate:"required,min=1"`
	CacheDir      string            `yaml:"cache_dir" validate:"omitempty,dir"`
}

type TarSSHConfig struct {
	Target          string `yaml:"target" validate:"required,dir"`
	SSHServer       string `yaml:"ssh_server" validate:"required"`
	OpenSSLType     string `yaml:"openssl_type" validate:"required"`
	OpenSSLPassword string `yaml:"openssl_password" validate:"required"`
	FileName        string `yaml:"file_name" validate:"required"`
}

// Load reads and parses YAML configuration from the specified path,
// expands environment variables, and validates structure constraints.
func Load(configPath string) (*Config, error) {
	fileBytes, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	expandedContent := os.ExpandEnv(string(fileBytes))

	var parsedConfig Config
	if err := yaml.Unmarshal([]byte(expandedContent), &parsedConfig); err != nil {
		return nil, fmt.Errorf("failed to unmarshal YAML: %w", err)
	}

	if parsedConfig.App.TimeZone == "" {
		parsedConfig.App.TimeZone = "UTC"
	}
	if parsedConfig.App.LogLevel == "" {
		parsedConfig.App.LogLevel = "info"
	}

	structValidator := validator.New(validator.WithRequiredStructEnabled())
	if err := structValidator.Struct(&parsedConfig); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %w", err)
	}

	location, err := time.LoadLocation(parsedConfig.App.TimeZone)
	if err != nil {
		return nil, fmt.Errorf("invalid timezone %q: %w", parsedConfig.App.TimeZone, err)
	}
	time.Local = location

	return &parsedConfig, nil
}
