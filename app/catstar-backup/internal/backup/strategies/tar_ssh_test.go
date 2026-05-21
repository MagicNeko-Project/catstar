package strategies

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

func createPipelineTestDeps() (*config.Config, *slog.Logger, *notify.CompositeNotifier) {
	cfg := &config.Config{
		App: config.AppConfig{
			MachineName: "TestHost",
		},
		Notifications: config.NotificationsConfig{
			SendVerbose: false,
		},
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	dummyHTTP := &http.Client{}
	notifier := notify.NewCompositeNotifier(cfg, logger, dummyHTTP)
	return cfg, logger, notifier
}

func getTarSSHJobConfig() *config.TarSSHConfig {
	return &config.TarSSHConfig{
		Target:          "/",
		SSHServer:       "user@host",
		OpenSSLType:     "aes-128-cbc",
		OpenSSLPassword: "supersecretpassword",
		FileName:        "test-%(%F_%H%M%S)T.tar.zst",
	}
}

func TestTarSSHPipeline_DataFlow(t *testing.T) {
	cfg, logger, notifier := createPipelineTestDeps()
	mockFactory := NewMockCommandFactory()

	// Set up custom pipeline mock handlers to verify streaming data flow
	mockFactory.CustomHandlers["tar"] = func(p *MockProcess) error {
		_, err := p.Stdout.Write([]byte("original-data"))
		return err
	}

	mockFactory.CustomHandlers["openssl"] = func(p *MockProcess) error {
		// Verify password from Env
		hasPass := false
		for _, env := range p.Env {
			if env == "CATSTAR_SSL_PASS=supersecretpassword" {
				hasPass = true
			}
		}
		if !hasPass {
			return fmt.Errorf("missing openssl password in env")
		}

		data, err := io.ReadAll(p.Stdin)
		if err != nil {
			return err
		}
		_, err = p.Stdout.Write([]byte(string(data) + "-encrypted"))
		return err
	}

	mockFactory.CustomHandlers["dd"] = func(p *MockProcess) error {
		data, err := io.ReadAll(p.Stdin)
		if err != nil {
			return err
		}
		_, err = p.Stdout.Write([]byte(string(data) + "-dd"))
		return err
	}

	var sshInput string
	var sshInputMu sync.Mutex
	mockFactory.CustomHandlers["ssh"] = func(p *MockProcess) error {
		data, err := io.ReadAll(p.Stdin)
		if err != nil {
			return err
		}
		sshInputMu.Lock()
		sshInput = string(data)
		sshInputMu.Unlock()
		return nil
	}

	jobCfg := getTarSSHJobConfig()
	mockClock := clock.NewMockClock(time.Date(2026, 5, 21, 12, 0, 0, 0, time.UTC))

	engine := NewTarSSHEngine("tar_job", cfg.App.MachineName, cfg.Notifications.SendVerbose, jobCfg, logger, notifier, mockFactory, mockClock)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("pipeline execution failed: %v", err)
	}

	// Verify that exactly 4 processes were created and started
	if len(mockFactory.Processes) != 4 {
		t.Fatalf("expected 4 processes, got %d", len(mockFactory.Processes))
	}

	var opensslProc *MockProcess
	var sshProc *MockProcess

	for _, p := range mockFactory.Processes {
		if !p.started {
			t.Errorf("expected process %s to be started", p.Name)
		}
		if !p.waited {
			t.Errorf("expected process %s to be waited", p.Name)
		}

		if p.Name == "openssl" {
			opensslProc = p
		}
		if p.Name == "ssh" {
			sshProc = p
		}
	}

	// Assertion 1: OpenSSL Security Injection
	if opensslProc == nil {
		t.Fatalf("openssl process was not created")
	}
	hasPass := false
	for _, envVar := range opensslProc.Env {
		if envVar == "CATSTAR_SSL_PASS=supersecretpassword" {
			hasPass = true
			break
		}
	}
	if !hasPass {
		t.Fatalf("openssl process did not receive securely injected password in its environment map")
	}

	// Assertion 2: Streaming Pipeline Data Verification
	sshInputMu.Lock()
	finalData := sshInput
	sshInputMu.Unlock()

	expectedData := "original-data-encrypted-dd"
	if finalData != expectedData {
		t.Errorf("expected final streaming data %q, got %q", expectedData, finalData)
	}

	// Assertion 3: Time/Clock-based File Name formatting Verification
	if sshProc == nil {
		t.Fatalf("ssh process was not created")
	}
	expectedFileName := "test-2026-05-21_120000.tar.zst"
	expectedSSHCmd := fmt.Sprintf("cat > '%s'", expectedFileName)
	if !strings.Contains(sshProc.FullCmd, expectedSSHCmd) {
		t.Errorf("expected ssh target filename to contain %q, got %q", expectedSSHCmd, sshProc.FullCmd)
	}
}

func TestTarSSHPipeline_ContextCancellation(t *testing.T) {
	cfg, logger, notifier := createPipelineTestDeps()
	mockFactory := NewMockCommandFactory()
	mockFactory.FailOnCreate = "ssh"

	jobCfg := getTarSSHJobConfig()
	mockClock := clock.NewMockClock(time.Date(2026, 5, 21, 12, 0, 0, 0, time.UTC))

	engine := NewTarSSHEngine("tar_job", cfg.App.MachineName, cfg.Notifications.SendVerbose, jobCfg, logger, notifier, mockFactory, mockClock)

	err := engine.Execute(context.Background())
	if err == nil {
		t.Fatalf("expected pipeline to fail when ssh process fails to start")
	}

	// Verify the error bubbles up correctly, identifying the failure point
	if !strings.Contains(err.Error(), "ssh") {
		t.Errorf("expected error to originate from ssh process, got: %v", err)
	}
}
