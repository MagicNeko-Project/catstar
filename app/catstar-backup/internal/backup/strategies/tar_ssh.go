package strategies

import (
	"context"
	"fmt"
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
	cfg      *config.AppConfig
	logger   *slog.Logger
	notifier *notify.CompositeNotifier
	factory  CommandFactory
}

func NewTarSSHEngine(cfg *config.AppConfig, logger *slog.Logger, notifier *notify.CompositeNotifier, factory CommandFactory) *TarSSHEngine {
	return &TarSSHEngine{cfg: cfg, logger: logger, notifier: notifier, factory: factory}
}

func (e *TarSSHEngine) Name() string { return "tar_ssh" }

func (e *TarSSHEngine) Execute(ctx context.Context) error {
	e.logger.Info("Executing Tar SSH Backup Pipeline")
	if e.cfg.NotifySendVerbose {
		e.notifier.Send(ctx, fmt.Sprintf("%s 开始备份：tar.zst", e.cfg.MachineName))
	}

	// This errgroup shares a cancelable context. If *any* process fails,
	// the context is canceled, signaling all active processes instantly.
	eg, egCtx := errgroup.WithContext(ctx)

	// Replace the simple bash date format for the target filename
	fileName := strings.ReplaceAll(e.cfg.TarFileName, "%(%F_%H%M%S)T", time.Now().Format("2006-01-02_150405"))

	// 1. Create native Go processes via the abstract factory
	tarCmd := e.factory.Create(egCtx, "tar", "-I", "zstd", "-cp", "--one-file-system", "/")
	
	// SECURITY: Instead of `-k`, we explicitly use `-pass env:CATSTAR_SSL_PASS`
	sslCmd := e.factory.Create(egCtx, "openssl", e.cfg.TarOpenSSLType, "-salt", "-pass", "env:CATSTAR_SSL_PASS")
	
	ddCmd := e.factory.Create(egCtx, "dd", "bs=64K")
	
	sshCmd := e.factory.Create(egCtx, "ssh", e.cfg.TarSSHServer, fmt.Sprintf("cat > '%s'", fileName))

	// 2. Safely inject the OpenSSL password strictly into that process's environment space.
	sslCmd.SetEnv(append(os.Environ(), "CATSTAR_SSL_PASS="+e.cfg.TarOpenSSLPassword))

	// 3. Chain Stdio Pipes
	tarOut, err := tarCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create tar stdout pipe: %w", err)
	}
	sslCmd.SetStdin(tarOut)

	sslOut, err := sslCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create openssl stdout pipe: %w", err)
	}
	ddCmd.SetStdin(sslOut)

	ddOut, err := ddCmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create dd stdout pipe: %w", err)
	}
	sshCmd.SetStdin(ddOut)

	// 4. Route telemetry directly to slog instead of a generic shell output buffer
	tarCmd.SetStderr(newSlogWriter(e.logger, "error", "tar"))
	sslCmd.SetStderr(newSlogWriter(e.logger, "error", "openssl"))
	ddCmd.SetStderr(newSlogWriter(e.logger, "error", "dd"))
	sshCmd.SetStderr(newSlogWriter(e.logger, "error", "ssh"))

	// 5. Orchestrate concurrently
	processes := []Process{tarCmd, sslCmd, ddCmd, sshCmd}
	for _, p := range processes {
		proc := p // Shadow for closure
		eg.Go(func() error {
			if err := proc.Start(); err != nil {
				return fmt.Errorf("failed to start process: %w", err)
			}
			return proc.Wait()
		})
	}

	// 6. Wait for resolution. Will return the first error encountered, cancelling the rest.
	if err := eg.Wait(); err != nil {
		e.logger.Error("Tar SSH Pipeline failed", "error", err)
		return err
	}

	e.logger.Info("Tar SSH Pipeline completed successfully")
	return nil
}
