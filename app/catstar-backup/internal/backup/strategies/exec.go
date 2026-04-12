package strategies

import (
	"context"
	"io"
	"log/slog"
	"os/exec"
)

// Process abstracts an OS process lifecycle, enabling 100% test coverage
// without executing system binaries or writing to disk.
type Process interface {
	Start() error
	Wait() error
	StdoutPipe() (io.ReadCloser, error)
	StdinPipe() (io.WriteCloser, error)
	SetStdin(io.Reader)
	SetStdout(io.Writer)
	SetStderr(io.Writer)
	SetEnv([]string)
}

// CommandFactory provides a standardized way to instantiate processes
// safely and independently.
type CommandFactory interface {
	Create(ctx context.Context, name string, args ...string) Process
}

// DefaultCommandFactory wraps the native os/exec package.
type DefaultCommandFactory struct {
	logger *slog.Logger
}

func NewDefaultCommandFactory(logger *slog.Logger) *DefaultCommandFactory {
	return &DefaultCommandFactory{logger: logger}
}

func (d *DefaultCommandFactory) Create(ctx context.Context, name string, args ...string) Process {
	return &DefaultProcess{
		cmd:    exec.CommandContext(ctx, name, args...),
		logger: d.logger,
	}
}

// DefaultProcess is a 1-to-1 wrapper over the standard *exec.Cmd struct.
type DefaultProcess struct {
	cmd    *exec.Cmd
	logger *slog.Logger
}

func (p *DefaultProcess) Start() error {
	p.logger.Debug("Starting process", "cmd", p.cmd.Path, "args", p.cmd.Args)
	return p.cmd.Start()
}

func (p *DefaultProcess) Wait() error {
	err := p.cmd.Wait()
	if err != nil {
		p.logger.Error("Process exited with error", "cmd", p.cmd.Path, "error", err)
	} else {
		p.logger.Debug("Process exited cleanly", "cmd", p.cmd.Path)
	}
	return err
}

func (p *DefaultProcess) StdoutPipe() (io.ReadCloser, error) {
	return p.cmd.StdoutPipe()
}

func (p *DefaultProcess) StdinPipe() (io.WriteCloser, error) {
	return p.cmd.StdinPipe()
}

func (p *DefaultProcess) SetStdin(r io.Reader) {
	p.cmd.Stdin = r
}

func (p *DefaultProcess) SetStdout(w io.Writer) {
	p.cmd.Stdout = w
}

func (p *DefaultProcess) SetStderr(w io.Writer) {
	p.cmd.Stderr = w
}

func (p *DefaultProcess) SetEnv(env []string) {
	p.cmd.Env = env
}

// Helper to run a simple, blocking command using the factory (for simple strategies).
func runSimpleCommand(ctx context.Context, factory CommandFactory, logger *slog.Logger, cmdStr string, args ...string) error {
	cmd := factory.Create(ctx, cmdStr, args...)

	// Create an inline writer that pipes output straight to slog for simple tracking
	writer := newSlogWriter(logger, "info", cmdStr)
	cmd.SetStdout(writer)
	cmd.SetStderr(writer)

	if err := cmd.Start(); err != nil {
		return err
	}
	return cmd.Wait()
}

type slogWriter struct {
	logger *slog.Logger
	level  string
	prefix string
}

func newSlogWriter(logger *slog.Logger, level, prefix string) *slogWriter {
	return &slogWriter{logger: logger, level: level, prefix: prefix}
}

func (w *slogWriter) Write(p []byte) (n int, err error) {
	w.logger.Info("Process Output", "cmd", w.prefix, "output", string(p))
	return len(p), nil
}
