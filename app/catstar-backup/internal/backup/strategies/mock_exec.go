package strategies

import (
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
)

type MockCommandFactory struct {
	mutex          sync.Mutex
	Processes      []*MockProcess
	FailOnCreate   string
	CustomHandlers map[string]func(process *MockProcess) error
	OnCreate       func(process *MockProcess)
}

func NewMockCommandFactory() *MockCommandFactory {
	return &MockCommandFactory{
		CustomHandlers: make(map[string]func(process *MockProcess) error),
	}
}

func (factory *MockCommandFactory) Create(ctx context.Context, commandName string, arguments ...string) Process {
	factory.mutex.Lock()
	defer factory.mutex.Unlock()

	fullCommand := commandName
	if len(arguments) > 0 {
		fullCommand = commandName + " " + strings.Join(arguments, " ")
	}

	process := &MockProcess{
		Name:        commandName,
		Args:        arguments,
		FullCommand: fullCommand,
		Environment: make([]string, 0),
	}

	if factory.FailOnCreate != "" && commandName == factory.FailOnCreate {
		process.FailOnStart = true
	}

	if factory.CustomHandlers != nil {
		if customHandler, exists := factory.CustomHandlers[commandName]; exists {
			process.RunFunc = customHandler
		}
	}

	if process.RunFunc == nil {
		process.RunFunc = func(mockProcess *MockProcess) error {
			if mockProcess.Stdin != nil {
				_, _ = io.Copy(io.Discard, mockProcess.Stdin)
			}
			if mockProcess.Name == "tar" {
				if mockProcess.Stdout != nil {
					_, _ = mockProcess.Stdout.Write([]byte("mock-tar-data"))
				}
			}
			if mockProcess.Name == "openssl" {
				if mockProcess.Stdout != nil {
					_, _ = mockProcess.Stdout.Write([]byte("mock-tar-data-encrypted"))
				}
			}
			return nil
		}
	}

	if factory.OnCreate != nil {
		factory.OnCreate(process)
	}

	factory.Processes = append(factory.Processes, process)
	return process
}

type MockProcess struct {
	mutex       sync.Mutex
	Name        string
	Args        []string
	FullCommand string
	Environment []string

	Stdin  io.Reader
	Stdout io.Writer
	Stderr io.Writer

	RunFunc func(process *MockProcess) error

	FailOnStart bool
	FailOnWait  bool

	errorChannel chan error
	started      bool
	waited       bool
}

func (process *MockProcess) Start() error {
	process.mutex.Lock()
	defer process.mutex.Unlock()

	if process.started {
		return fmt.Errorf("mock process %s already started", process.Name)
	}
	process.started = true

	if process.FailOnStart {
		return fmt.Errorf("mock Start() failure for %s", process.Name)
	}

	process.errorChannel = make(chan error, 1)

	go func() {
		var err error
		if process.RunFunc != nil {
			err = process.RunFunc(process)
		}

		if pipeWriter, ok := process.Stdout.(*io.PipeWriter); ok {
			_ = pipeWriter.CloseWithError(err)
		}

		process.errorChannel <- err
	}()

	return nil
}

func (process *MockProcess) Wait() error {
	process.mutex.Lock()
	if !process.started {
		process.mutex.Unlock()
		return fmt.Errorf("mock process %s not started", process.Name)
	}
	if process.waited {
		process.mutex.Unlock()
		return fmt.Errorf("mock process %s already waited", process.Name)
	}
	process.waited = true
	process.mutex.Unlock()

	err := <-process.errorChannel
	if err == nil && process.FailOnWait {
		return fmt.Errorf("mock Wait() failure for %s", process.Name)
	}
	return err
}

func (process *MockProcess) StdoutPipe() (io.ReadCloser, error) {
	process.mutex.Lock()
	defer process.mutex.Unlock()

	if process.started {
		return nil, fmt.Errorf("StdoutPipe called after process %s started", process.Name)
	}
	if process.Stdout != nil {
		return nil, fmt.Errorf("stdout already set for process %s", process.Name)
	}
	pipeReader, pipeWriter := io.Pipe()
	process.Stdout = pipeWriter
	return pipeReader, nil
}

func (process *MockProcess) StdinPipe() (io.WriteCloser, error) {
	process.mutex.Lock()
	defer process.mutex.Unlock()

	if process.started {
		return nil, fmt.Errorf("StdinPipe called after process %s started", process.Name)
	}
	if process.Stdin != nil {
		return nil, fmt.Errorf("stdin already set for process %s", process.Name)
	}
	pipeReader, pipeWriter := io.Pipe()
	process.Stdin = pipeReader
	return pipeWriter, nil
}

func (process *MockProcess) SetStdin(reader io.Reader) {
	process.mutex.Lock()
	defer process.mutex.Unlock()
	process.Stdin = reader
}

func (process *MockProcess) SetStdout(writer io.Writer) {
	process.mutex.Lock()
	defer process.mutex.Unlock()
	process.Stdout = writer
}

func (process *MockProcess) SetStderr(writer io.Writer) {
	process.mutex.Lock()
	defer process.mutex.Unlock()
	process.Stderr = writer
}

func (process *MockProcess) SetEnv(environmentVariables []string) {
	process.mutex.Lock()
	defer process.mutex.Unlock()
	process.Environment = environmentVariables
}
