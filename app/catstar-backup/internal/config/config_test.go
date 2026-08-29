package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadAndValidateYAML(t *testing.T) {
	tempDirectory := t.TempDir()
	configPath := filepath.Join(tempDirectory, "config.yaml")

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

	t.Setenv("TEST_TELEGRAM_TOKEN", "123:ABC")
	t.Setenv("TEST_RESTIC_PASS", "supersecret")

	parsedConfig, err := Load(configPath)
	if err != nil {
		t.Fatalf("expected valid config, got error: %v", err)
	}

	if parsedConfig.App.MachineName != "Test-Node" {
		t.Errorf("expected machine name 'Test-Node', got %q", parsedConfig.App.MachineName)
	}

	if parsedConfig.Notifications.Telegram.BotToken != "123:ABC" {
		t.Errorf("expected expanded telegram token '123:ABC', got %q", parsedConfig.Notifications.Telegram.BotToken)
	}

	if len(parsedConfig.Jobs) != 1 {
		t.Fatalf("expected 1 job, got %d", len(parsedConfig.Jobs))
	}

	primaryJob := parsedConfig.Jobs[0]
	if primaryJob.Name != "system_root" {
		t.Errorf("expected job name 'system_root', got %q", primaryJob.Name)
	}
	if primaryJob.Restic.Password != "supersecret" {
		t.Errorf("expected expanded restic password 'supersecret', got %q", primaryJob.Restic.Password)
	}
}

func TestValidationFailures(t *testing.T) {
	testCases := []struct {
		name        string
		yamlContent string
	}{
		{
			name: "MissingMachineNameAndInvalidTimezone",
			yamlContent: `
app:
  timezone: "Invalid/Zone"
jobs:
  - name: "test_job"
    type: "invalid_type"
`,
		},
		{
			name: "InvalidURLInDiscordWebhook",
			yamlContent: `
app:
  machine_name: "Node-1"
  timezone: "UTC"
notifications:
  discord:
    webhook_url: "not-a-valid-url"
    username: "backup-bot"
`,
		},
		{
			name: "InvalidSummaryHoursOutOfRange",
			yamlContent: `
app:
  machine_name: "Node-1"
  timezone: "UTC"
notifications:
  summary_hours: [25]
`,
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(subtest *testing.T) {
			tempDirectory := subtest.TempDir()
			configPath := filepath.Join(tempDirectory, "config_bad.yaml")

			if err := os.WriteFile(configPath, []byte(testCase.yamlContent), 0644); err != nil {
				subtest.Fatalf("failed to write test config file: %v", err)
			}

			_, err := Load(configPath)
			if err == nil {
				subtest.Fatalf("expected validation error for invalid config, got nil")
			}
		})
	}
}
