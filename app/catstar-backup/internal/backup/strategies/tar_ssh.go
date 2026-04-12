package strategies

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/MagicNeko-Project/catstar-backup/internal/config"
	"github.com/MagicNeko-Project/catstar-backup/internal/notify"
)

// TarSSHEngine constructs and orchestrates a robust native Go pipeline:
// tar | openssl | dd | ssh
// It guarantees 0 zombie processes and secures the OpenSSL password via environment variables.
type TarSSHEngine struct {
	jobName  string
	machine  string
	verbose  bool
	cfg      *config.TarSSHConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	factory  CommandFactory
}

func NewTarSSHEngine(jobName, machineName string, verbose bool, cfg *config.TarSSHConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, factory CommandFactory) *TarSSHEngine {
	return &TarSSHEngine{
		jobName:  jobName,
		machine:  machineName,
		verbose:  verbose,
		cfg:      cfg,
		logger:   logger.With("job", jobName),
		notifier: notifier,
		factory:  factory,
	}
}

func (e *TarSSHEngine) Name() string { return e.jobName }

func (e *TarSSHEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Tar SSH Backup Pipeline")
	if e.verbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份 (%s)：tar.zst", e.machine, e.jobName))
	}

	eg, egCtx := errgroup.WithContext(ctx)

	// Replace the simple bash date format for the target filename
	fileName := strings.ReplaceAll(e.cfg.FileName, "%(%F_%H%M%S)T", time.Now().Format("2006-01-02_150405"))

	tarCmd := e.factory.Create(egCtx, "tar", "-I", "zstd", "-cp", "--one-file-system", e.cfg.Target)
	sslCmd := e.factory.Create(egCtx, "openssl", e.cfg.OpenSSLType, "-salt", "-pass", "env:CATSTAR_SSL_PASS")
	ddCmd := e.factory.Create(egCtx, "dd", "bs=64K")
	sshCmd := e.factory.Create(egCtx, "ssh", e.cfg.SSHServer, fmt.Sprintf("cat > '%s'", fileName))

	sslCmd.SetEnv(append(os.Environ(), "CATSTAR_SSL_PASS="+e.cfg.OpenSSLPassword))

	var pipesToClose []io.Closer
	defer func() {
		for _, p := range pipesToClose {
			p.Close()
		}
	}()

	tarOut, err := tarCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create tar stdout pipe: %w", err)
	}
	pipesToClose = append(pipesToClose, tarOut)
	sslCmd.SetStdin(tarOut)

	sslOut, err := sslCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create openssl stdout pipe: %w", err)
	}
	pipesToClose = append(pipesToClose, sslOut)
	ddCmd.SetStdin(sslOut)

	ddOut, err := ddCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create dd stdout pipe: %w", err)
	}
	pipesToClose = append(pipesToClose, ddOut)
	sshCmd.SetStdin(ddOut)

	pipesToClose = nil

	tarCmd.SetStderr(newSlogWriter(e.logger, "error", "tar"))
	sslCmd.SetStderr(newSlogWriter(e.logger, "error", "openssl"))
	ddCmd.SetStderr(newSlogWriter(e.logger, "error", "dd"))
	sshCmd.SetStderr(newSlogWriter(e.logger, "error", "ssh"))

	processes := []Process{tarCmd, sslCmd, ddCmd, sshCmd}
	for _, p := range processes {
		eg.Go(func() error {
			if err := p.Start(); err != nil {
				return fmt.Errorf("failed to start process: %w", err)
			}
			return p.Wait()
		})
	}

	if err := eg.Wait(); err != nil {
		e.logger.Error("Tar SSH Pipeline failed", "error", err)
		return err
	}

	e.logger.Info("Tar SSH Pipeline completed successfully")
	return nil
}
