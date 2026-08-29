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

func createPipelineTestDependencies() (*config.Config, *slog.Logger, *notify.CompositeNotifier) {
	testConfig := &config.Config{
		App: config.AppConfig{
			MachineName: "TestHost",
		},
		Notifications: config.NotificationsConfig{
			SendVerbose: false,
		},
	}
	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	dummyHTTP := &http.Client{}
	compositeNotifier := notify.NewCompositeNotifier(testConfig, discardLogger, dummyHTTP)
	return testConfig, discardLogger, compositeNotifier
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
	testConfig, logger, notifier := createPipelineTestDependencies()
	mockFactory := NewMockCommandFactory()

	mockFactory.CustomHandlers["tar"] = func(process *MockProcess) error {
		_, err := process.Stdout.Write([]byte("original-data"))
		return err
	}

	mockFactory.CustomHandlers["openssl"] = func(process *MockProcess) error {
		hasPassword := false
		for _, environmentVariable := range process.Environment {
			if environmentVariable == "CATSTAR_SSL_PASS=supersecretpassword" {
				hasPassword = true
			}
		}
		if !hasPassword {
			return fmt.Errorf("missing openssl password in env")
		}

		data, err := io.ReadAll(process.Stdin)
		if err != nil {
			return err
		}
		_, err = process.Stdout.Write([]byte(string(data) + "-encrypted"))
		return err
	}

	mockFactory.CustomHandlers["dd"] = func(process *MockProcess) error {
		data, err := io.ReadAll(process.Stdin)
		if err != nil {
			return err
		}
		_, err = process.Stdout.Write([]byte(string(data) + "-dd"))
		return err
	}

	var sshInputData string
	var sshInputMutex sync.Mutex
	mockFactory.CustomHandlers["ssh"] = func(process *MockProcess) error {
		data, err := io.ReadAll(process.Stdin)
		if err != nil {
			return err
		}
		sshInputMutex.Lock()
		sshInputData = string(data)
		sshInputMutex.Unlock()
		return nil
	}

	jobConfig := getTarSSHJobConfig()
	mockClock := clock.NewMockClock(time.Date(2026, 5, 21, 12, 0, 0, 0, time.UTC))

	engine := NewTarSSHEngine("tar_job", testConfig.App.MachineName, testConfig.Notifications.SendVerbose, jobConfig, logger, notifier, mockFactory, mockClock)

	err := engine.Execute(context.Background())
	if err != nil {
		t.Fatalf("pipeline execution failed: %v", err)
	}

	if len(mockFactory.Processes) != 4 {
		t.Fatalf("expected 4 processes, got %d", len(mockFactory.Processes))
	}

	var opensslProcess *MockProcess
	var sshProcess *MockProcess

	for _, process := range mockFactory.Processes {
		if !process.started {
			t.Errorf("expected process %s to be started", process.Name)
		}
		if !process.waited {
			t.Errorf("expected process %s to be waited", process.Name)
		}

		if process.Name == "openssl" {
			opensslProcess = process
		}
		if process.Name == "ssh" {
			sshProcess = process
		}
	}

	if opensslProcess == nil {
		t.Fatalf("openssl process was not created")
	}
	hasPassword := false
	for _, environmentVariable := range opensslProcess.Environment {
		if environmentVariable == "CATSTAR_SSL_PASS=supersecretpassword" {
			hasPassword = true
			break
		}
	}
	if !hasPassword {
		t.Fatalf("openssl process did not receive injected password in environment")
	}

	sshInputMutex.Lock()
	finalData := sshInputData
	sshInputMutex.Unlock()

	expectedData := "original-data-encrypted-dd"
	if finalData != expectedData {
		t.Errorf("expected final streaming data %q, got %q", expectedData, finalData)
	}

	if sshProcess == nil {
		t.Fatalf("ssh process was not created")
	}
	expectedFileName := "test-2026-05-21_120000.tar.zst"
	expectedSSHCommand := fmt.Sprintf("cat > '%s'", expectedFileName)
	if !strings.Contains(sshProcess.FullCommand, expectedSSHCommand) {
		t.Errorf("expected ssh target filename to contain %q, got %q", expectedSSHCommand, sshProcess.FullCommand)
	}
}

func TestTarSSHPipeline_ContextCancellation(t *testing.T) {
	testConfig, logger, notifier := createPipelineTestDependencies()
	mockFactory := NewMockCommandFactory()
	mockFactory.FailOnCreate = "ssh"

	jobConfig := getTarSSHJobConfig()
	mockClock := clock.NewMockClock(time.Date(2026, 5, 21, 12, 0, 0, 0, time.UTC))

	engine := NewTarSSHEngine("tar_job", testConfig.App.MachineName, testConfig.Notifications.SendVerbose, jobConfig, logger, notifier, mockFactory, mockClock)

	err := engine.Execute(context.Background())
	if err == nil {
		t.Fatalf("expected pipeline to fail when ssh process fails to start")
	}

	if !strings.Contains(err.Error(), "ssh") {
		t.Errorf("expected error to originate from ssh process, got: %v", err)
	}
}
