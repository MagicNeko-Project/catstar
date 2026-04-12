package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadAndValidateYAML(t *testing.T) {
	// Create a temporary YAML config file
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.yaml")

	yamlContent := `
app:
  machine_name: "Test-Node"
  timezone: "UTC"
  log_level: "debug"

notifications:
  send_summary: true
  send_verbose: false
  telegram:
    bot_token: "${TEST_TELEGRAM_TOKEN}"
    chat_id: "98765"

jobs:
  - name: "system_root"
    type: "restic"
    restic:
      root: "/tmp"
      repository: "s3:example.com/bucket"
      password: "${TEST_RESTIC_PASS}"
`
	if err := os.WriteFile(configPath, []byte(yamlContent), 0644); err != nil {
		t.Fatalf("failed to write test config file: %v", err)
	}

	// Inject secure secrets directly via the environment
	t.Setenv("TEST_TELEGRAM_TOKEN", "123:ABC")
	t.Setenv("TEST_RESTIC_PASS", "supersecret")

	cfg, err := Load(configPath)
	if err != nil {
		t.Fatalf("expected valid config, got error: %v", err)
	}

	// Assertions to verify struct mapping
	if cfg.App.MachineName != "Test-Node" {
		t.Errorf("expected machine name 'Test-Node', got %q", cfg.App.MachineName)
	}

	// Assertions to verify os.ExpandEnv interpolation worked safely
	if cfg.Notifications.Telegram.BotToken != "123:ABC" {
		t.Errorf("expected expanded telegram token '123:ABC', got %q", cfg.Notifications.Telegram.BotToken)
	}

	if len(cfg.Jobs) != 1 {
		t.Fatalf("expected 1 job, got %d", len(cfg.Jobs))
	}

	job := cfg.Jobs[0]
	if job.Name != "system_root" {
		t.Errorf("expected job name 'system_root', got %q", job.Name)
	}
	if job.Restic.Password != "supersecret" {
		t.Errorf("expected expanded restic password 'supersecret', got %q", job.Restic.Password)
	}
}

func TestValidationFailures(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config_bad.yaml")

	// Missing machine_name (required) and invalid timezone
	yamlContent := `
app:
  timezone: "Invalid/Zone"
jobs:
  - name: "test_job"
    type: "invalid_type"
`
	if err := os.WriteFile(configPath, []byte(yamlContent), 0644); err != nil {
		t.Fatalf("failed to write test config file: %v", err)
	}

	_, err := Load(configPath)
	if err == nil {
		t.Fatalf("expected validation error for invalid config, got nil")
	}
}
