package strategies

import (
	"context"
	"io"
	"log/slog"
	"os/exec"
)

// Process abstracts command execution capabilities.
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

// CommandFactory creates Process instances for command execution.
type CommandFactory interface {
	Create(ctx context.Context, commandName string, arguments ...string) Process
}

type DefaultCommandFactory struct {
	logger *slog.Logger
}

func NewDefaultCommandFactory(logger *slog.Logger) *DefaultCommandFactory {
	return &DefaultCommandFactory{logger: logger}
}

func (factory *DefaultCommandFactory) Create(ctx context.Context, commandName string, arguments ...string) Process {
	return &DefaultProcess{
		command: exec.CommandContext(ctx, commandName, arguments...),
		logger:  factory.logger,
	}
}

type DefaultProcess struct {
	command *exec.Cmd
	logger  *slog.Logger
}

func (process *DefaultProcess) Start() error {
	process.logger.Debug("Starting process", "command", process.command.Path, "arguments", process.command.Args)
	return process.command.Start()
}

func (process *DefaultProcess) Wait() error {
	err := process.command.Wait()
	if err != nil {
		process.logger.Error("Process exited with error", "command", process.command.Path, "error", err)
	} else {
		process.logger.Debug("Process exited cleanly", "command", process.command.Path)
	}
	return err
}

func (process *DefaultProcess) StdoutPipe() (io.ReadCloser, error) {
	return process.command.StdoutPipe()
}

func (process *DefaultProcess) StdinPipe() (io.WriteCloser, error) {
	return process.command.StdinPipe()
}

func (process *DefaultProcess) SetStdin(reader io.Reader) {
	process.command.Stdin = reader
}

func (process *DefaultProcess) SetStdout(writer io.Writer) {
	process.command.Stdout = writer
}

func (process *DefaultProcess) SetStderr(writer io.Writer) {
	process.command.Stderr = writer
}

func (process *DefaultProcess) SetEnv(environmentVariables []string) {
	process.command.Env = environmentVariables
}

func runSimpleCommand(
	ctx context.Context,
	factory CommandFactory,
	logger *slog.Logger,
	commandName string,
	arguments ...string,
) error {
	process := factory.Create(ctx, commandName, arguments...)

	outputWriter := newSlogWriter(logger, slog.LevelInfo, commandName)
	process.SetStdout(outputWriter)
	process.SetStderr(outputWriter)

	if err := process.Start(); err != nil {
		return err
	}
	return process.Wait()
}

type slogWriter struct {
	logger *slog.Logger
	level  slog.Level
	prefix string
}

func newSlogWriter(logger *slog.Logger, level slog.Level, prefix string) *slogWriter {
	return &slogWriter{logger: logger, level: level, prefix: prefix}
}

func (writer *slogWriter) Write(payload []byte) (int, error) {
	writer.logger.Log(context.Background(), writer.level, "Process Output", "command", writer.prefix, "output", string(payload))
	return len(payload), nil
}
