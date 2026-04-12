package config

import (
	"fmt"
	"os"
	"time"

	"github.com/go-playground/validator/v10"
	"gopkg.in/yaml.v3"
)

// Config represents the root configuration structure for Catstar Backup.
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

// NotificationsConfig defines all possible notification sinks and settings.
type NotificationsConfig struct {
	SendSummary      bool  `yaml:"send_summary"`
	SendVerbose      bool  `yaml:"send_verbose"`
	SummaryHours     []int `yaml:"summary_hours" validate:"omitempty,dive,min=0,max=23"`
	Telegram         *TelegramConfig `yaml:"telegram,omitempty"`
	Discord          *DiscordConfig  `yaml:"discord,omitempty"`
	Debug            *DebugConfig    `yaml:"debug,omitempty"`
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

// TelemetryConfig defines HTTP endpoints for logging and status tracking.
type TelemetryConfig struct {
	PingStartURL      string `yaml:"ping_start_url" validate:"omitempty,url"`
	PingEndURL        string `yaml:"ping_end_url" validate:"omitempty,url"`
	PingAppendStatus  bool   `yaml:"ping_append_status"`
	JournalUploadURL  string `yaml:"journal_upload_url" validate:"omitempty,url"`
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

// Load reads the YAML configuration file from the specified path, performs
// environment variable expansion (e.g., ${RESTIC_PASSWORD}), unmarshals it
// into the Config struct, and rigorously validates the structure.
func Load(path string) (*Config, error) {
	fileBytes, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	// 2026 Standard: Expand environment variables prior to parsing.
	// This prevents hardcoded secrets in the YAML file.
	expandedYAML := os.ExpandEnv(string(fileBytes))

	var cfg Config
	if err := yaml.Unmarshal([]byte(expandedYAML), &cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal YAML: %w", err)
	}

	// Set sane defaults where optional
	if cfg.App.TimeZone == "" {
		cfg.App.TimeZone = "UTC"
	}
	if cfg.App.LogLevel == "" {
		cfg.App.LogLevel = "info"
	}

	// Validate the complete structure
	validate := validator.New(validator.WithRequiredStructEnabled())
	if err := validate.Struct(&cfg); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %w", err)
	}

	// Globally apply timezone
	if loc, err := time.LoadLocation(cfg.App.TimeZone); err == nil {
		time.Local = loc
	} else {
		return nil, fmt.Errorf("invalid timezone %q: %w", cfg.App.TimeZone, err)
	}

	return &cfg, nil
}
