package strategies

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"

	"golang.org/x/sync/errgroup"

	"github.com/MagicNeko-Project/catstar-backup/internal/clock"
	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

const defaultStreamingBlockSize = "bs=64K"

// TarSSHEngine runs a streaming backup pipeline: tar | openssl | dd | ssh.
type TarSSHEngine struct {
	jobName        string
	machineName    string
	verbose        bool
	config         *config.TarSSHConfig
	logger         *slog.Logger
	notifier       *notify.CompositeNotifier
	commandFactory CommandFactory
	clockProvider  clock.Provider
}

func NewTarSSHEngine(
	jobName string,
	machineName string,
	verbose bool,
	tarSSHConfig *config.TarSSHConfig,
	logger *slog.Logger,
	notifier *notify.CompositeNotifier,
	commandFactory CommandFactory,
	clockProvider clock.Provider,
) *TarSSHEngine {
	return &TarSSHEngine{
		jobName:        jobName,
		machineName:    machineName,
		verbose:        verbose,
		config:         tarSSHConfig,
		logger:         logger.With("job", jobName),
		notifier:       notifier,
		commandFactory: commandFactory,
		clockProvider:  clockProvider,
	}
}

func (engine *TarSSHEngine) Name() string { return engine.jobName }

func (engine *TarSSHEngine) Execute(ctx context.Context) error {
	engine.logger.Info("Executing Tar SSH Backup Pipeline")
	if engine.verbose {
		engine.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：tar.zst", engine.machineName, engine.jobName))
	}

	pipelineGroup, pipelineContext := errgroup.WithContext(ctx)

	formattedTimestamp := engine.clockProvider.Now().Format("2006-01-02_150405")
	targetFileName := strings.ReplaceAll(engine.config.FileName, "%(%F_%H%M%S)T", formattedTimestamp)

	tarCommand := engine.commandFactory.Create(pipelineContext, "tar", "-I", "zstd", "-cp", "--one-file-system", engine.config.Target)
	sslCommand := engine.commandFactory.Create(pipelineContext, "openssl", engine.config.OpenSSLType, "-salt", "-pass", "env:CATSTAR_SSL_PASS")
	ddCommand := engine.commandFactory.Create(pipelineContext, "dd", defaultStreamingBlockSize)
	sshCommand := engine.commandFactory.Create(pipelineContext, "ssh", engine.config.SSHServer, fmt.Sprintf("cat > '%s'", targetFileName))

	sslCommand.SetEnv(append(os.Environ(), "CATSTAR_SSL_PASS="+engine.config.OpenSSLPassword))

	var pipesToClose []io.Closer
	defer func() {
		for _, pipe := range pipesToClose {
			_ = pipe.Close()
		}
	}()

	tarStdout, err := tarCommand.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create tar stdout pipe: %w", err)
	}
	pipesToClose = append(pipesToClose, tarStdout)
	sslCommand.SetStdin(tarStdout)

	sslStdout, err := sslCommand.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create openssl stdout pipe: %w", err)
	}
	pipesToClose = append(pipesToClose, sslStdout)
	ddCommand.SetStdin(sslStdout)

	ddStdout, err := ddCommand.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create dd stdout pipe: %w", err)
	}
	pipesToClose = append(pipesToClose, ddStdout)
	sshCommand.SetStdin(ddStdout)

	pipesToClose = nil

	tarCommand.SetStderr(newSlogWriter(engine.logger, slog.LevelError, "tar"))
	sslCommand.SetStderr(newSlogWriter(engine.logger, slog.LevelError, "openssl"))
	ddCommand.SetStderr(newSlogWriter(engine.logger, slog.LevelError, "dd"))
	sshCommand.SetStderr(newSlogWriter(engine.logger, slog.LevelError, "ssh"))

	processes := []Process{tarCommand, sslCommand, ddCommand, sshCommand}
	for _, pipelineProcess := range processes {
		pipelineGroup.Go(func() error {
			if err := pipelineProcess.Start(); err != nil {
				return fmt.Errorf("failed to start pipeline process: %w", err)
			}
			return pipelineProcess.Wait()
		})
	}

	if err := pipelineGroup.Wait(); err != nil {
		engine.logger.Error("Tar SSH Pipeline failed", "error", err)
		return fmt.Errorf("pipeline execution failure: %w", err)
	}

	engine.logger.Info("Tar SSH Pipeline completed successfully")
	return nil
}
