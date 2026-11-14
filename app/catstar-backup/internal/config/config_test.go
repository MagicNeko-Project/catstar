package config

import (
	"fmt"
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
	t.Setenv("RESTIC_CACHE_DIR", "")
	t.Setenv("CACHE_DIRECTORY", "")

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
	if primaryJob.Restic.CacheDir != "" {
		t.Errorf("expected empty cache directory when unset, got %q", primaryJob.Restic.CacheDir)
	}
}

func TestCacheDirectoryResolution(t *testing.T) {
	sourceDir := t.TempDir()
	snapshotsDir := t.TempDir()
	systemdCacheDir := t.TempDir()
	secondaryCacheDir := t.TempDir()
	autoCreatedCacheDir := filepath.Join(t.TempDir(), "auto-created-by-restic")
	yamlCacheDir := t.TempDir()
	missingCacheDir := filepath.Join(t.TempDir(), "nonexistent")

	baseYAML := fmt.Sprintf(`
app:
  machine_name: "Test-Node"
  timezone: "UTC"
jobs:
  - name: "restic_job"
    type: "restic"
    restic:
      root: %q
      repository: "rest:https://backup.example.com/repo"
      password: "test-password"
  - name: "btrfs_job"
    type: "btrfs_restic"
    btrfs_restic:
      snapshots_root: %q
      repository: "rest:https://backup.example.com/btrfs"
      password: "test-password"
      subvolumes:
        root: "/"
`, sourceDir, snapshotsDir)

	yamlWithExplicitCache := fmt.Sprintf(`
app:
  machine_name: "Test-Node"
  timezone: "UTC"
jobs:
  - name: "restic_job"
    type: "restic"
    restic:
      root: %q
      repository: "rest:https://backup.example.com/repo"
      password: "test-password"
      cache_dir: %q
  - name: "btrfs_job"
    type: "btrfs_restic"
    btrfs_restic:
      snapshots_root: %q
      repository: "rest:https://backup.example.com/btrfs"
      password: "test-password"
      cache_dir: %q
      subvolumes:
        root: "/"
`, sourceDir, yamlCacheDir, snapshotsDir, yamlCacheDir)

	testCases := []struct {
		name            string
		yamlContent     string
		resticCacheEnv  string
		systemdCacheEnv string
		expectedCache   string
		expectError     bool
	}{
		{
			name:            "SystemdSingleCacheDirectory",
			yamlContent:     baseYAML,
			systemdCacheEnv: systemdCacheDir,
			expectedCache:   systemdCacheDir,
		},
		{
			name:            "SystemdColonDelimitedCacheDirectory",
			yamlContent:     baseYAML,
			systemdCacheEnv: systemdCacheDir + ":" + secondaryCacheDir,
			expectedCache:   systemdCacheDir,
		},
		{
			name:            "ExplicitResticCacheDirLeavesCacheDirUnset",
			yamlContent:     baseYAML,
			resticCacheEnv:  autoCreatedCacheDir,
			systemdCacheEnv: systemdCacheDir,
			expectedCache:   "",
		},
		{
			name:            "ExplicitYAMLCacheDirOverridesEnvironment",
			yamlContent:     yamlWithExplicitCache,
			resticCacheEnv:  autoCreatedCacheDir,
			systemdCacheEnv: systemdCacheDir,
			expectedCache:   yamlCacheDir,
		},
		{
			name:            "InvalidSystemdCacheDirectoryFailsValidation",
			yamlContent:     baseYAML,
			systemdCacheEnv: missingCacheDir,
			expectError:     true,
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(subtest *testing.T) {
			configPath := filepath.Join(subtest.TempDir(), "config.yaml")
			if err := os.WriteFile(configPath, []byte(testCase.yamlContent), 0644); err != nil {
				subtest.Fatalf("failed to write test config file: %v", err)
			}

			subtest.Setenv("RESTIC_CACHE_DIR", testCase.resticCacheEnv)
			subtest.Setenv("CACHE_DIRECTORY", testCase.systemdCacheEnv)

			parsedConfig, err := Load(configPath)
			if testCase.expectError {
				if err == nil {
					subtest.Fatalf("expected validation error, got nil")
				}
				return
			}
			if err != nil {
				subtest.Fatalf("expected valid config, got error: %v", err)
			}

			if parsedConfig.Jobs[0].Restic.CacheDir != testCase.expectedCache {
				subtest.Errorf("expected restic cache_dir %q, got %q", testCase.expectedCache, parsedConfig.Jobs[0].Restic.CacheDir)
			}
			if parsedConfig.Jobs[1].BtrfsRestic.CacheDir != testCase.expectedCache {
				subtest.Errorf("expected btrfs_restic cache_dir %q, got %q", testCase.expectedCache, parsedConfig.Jobs[1].BtrfsRestic.CacheDir)
			}
		})
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
