package config

import (
	"testing"
)

func TestGetEnvBool(t *testing.T) {
	tests := []struct {
		name     string
		envVal   string
		fallback bool
		expected bool
	}{
		{"Truthy 1", "1", false, true},
		{"Truthy true", "true", false, true},
		{"Truthy yes", "yes", false, true},
		{"Falsy 0", "0", true, false},
		{"Falsy false", "false", true, false},
		{"Falsy no", "no", true, false},
		{"Empty string", "", true, true},
		{"Invalid string", "invalid", true, true},
		{"Unset", "UNSET", false, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Construct a unique key so previous test runs don't interfere
			envKey := "TEST_ENV_BOOL_" + tt.name
			
			if tt.envVal != "UNSET" {
				t.Setenv(envKey, tt.envVal)
			}

			result := getEnvBool(envKey, tt.fallback)
			if result != tt.expected {
				t.Errorf("expected %v, got %v", tt.expected, result)
			}
		})
	}
}

func TestLoadAndValidate(t *testing.T) {
	t.Run("Valid Configuration", func(t *testing.T) {
		t.Setenv("MACHINE_NAME", "TestNode")
		t.Setenv("TELEGRAM_BOT_TOKEN", "12345:ABCDEF")
		t.Setenv("TELEGRAM_BOT_SendMsg_User", "987654")
		t.Setenv("NOTIFY_SEND_SUMMARY_HOURS", "8 20")
		t.Setenv("BTRFS_SNAPSHOT_root", "/")

		cfg, err := Load()
		if err != nil {
			t.Fatalf("expected no error, got %v", err)
		}

		if cfg.MachineName != "TestNode" {
			t.Errorf("expected TestNode, got %s", cfg.MachineName)
		}
		if len(cfg.NotifySendSummaryHours) != 2 || cfg.NotifySendSummaryHours[0] != 8 {
			t.Errorf("expected parsed summary hours, got %v", cfg.NotifySendSummaryHours)
		}
		if val, ok := cfg.BtrfsSnapshots["root"]; !ok || val != "/" {
			t.Errorf("expected dynamic BTRFS snapshot 'root': '/', got %v", cfg.BtrfsSnapshots)
		}
	})

	t.Run("Invalid Telegram Configuration", func(t *testing.T) {
		t.Setenv("TELEGRAM_BOT_TOKEN", "12345:ABCDEF")
		// Explicitly blank out the dependent field
		t.Setenv("TELEGRAM_BOT_SendMsg_User", "")

		_, err := Load()
		if err == nil {
			t.Fatalf("expected validation error for missing telegram user, got nil")
		}
	})
}
