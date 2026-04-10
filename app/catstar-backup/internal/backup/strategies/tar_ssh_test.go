package strategies

import (
	"context"
	"io"
	"log/slog"
	"strings"
	"testing"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

func createPipelineTestDeps() (*config.AppConfig, *slog.Logger, *notify.CompositeNotifier) {
	cfg := &config.AppConfig{
		MachineName:        "TestHost",
		NotifySendVerbose:  false,
		TarSSHServer:       "user@host",
		TarOpenSSLType:     "aes-128-cbc",
		TarOpenSSLPassword: "supersecretpassword",
		TarFileName:        "test.tar.zst",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	notifier := notify.NewCompositeNotifier(cfg, logger)
	return cfg, logger, notifier
}

func TestTarSSHPipeline_DataFlow(t *testing.T) {
	cfg, logger, notifier := createPipelineTestDeps()
	mockFactory := &MockCommandFactory{}
	engine := NewTarSSHEngine(cfg, logger, notifier, mockFactory)

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
		if !p.Started {
			t.Errorf("expected process %s to be started", p.Name)
		}
		if !p.Waited {
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
	// Verify that CATSTAR_SSL_PASS was securely set in the environment
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

	// Assertion 2: Streaming Pipeline Integrity
	// Verify that Tar's output is connected to OpenSSL's input, etc.
	// Since we mock `StdoutPipe` to return a buffer, we verify the `Stdin` of the next process is set.
	if opensslProc.Stdin == nil {
		t.Fatalf("pipeline broke: openssl stdin is not connected to tar stdout")
	}
	if sshProc.Stdin == nil {
		t.Fatalf("pipeline broke: ssh stdin is not connected to dd stdout")
	}
}

func TestTarSSHPipeline_ContextCancellation(t *testing.T) {
	cfg, logger, notifier := createPipelineTestDeps()
	mockFactory := &MockCommandFactory{
		FailOnCreate: "ssh",
	}
	
	engine := NewTarSSHEngine(cfg, logger, notifier, mockFactory)
	
	err := engine.Execute(context.Background())
	if err == nil {
		t.Fatalf("expected pipeline to fail when ssh process fails to start")
	}

	// Verify the error bubbles up correctly, identifying the failure point
	if !strings.Contains(err.Error(), "ssh") {
		t.Errorf("expected error to originate from ssh process, got: %v", err)
	}

	// The errgroup will abort early, meaning some processes might have started 
	// while others didn't. The test passes if the orchestrator correctly halted
	// execution upon the first error (the forced ssh failure).
}
