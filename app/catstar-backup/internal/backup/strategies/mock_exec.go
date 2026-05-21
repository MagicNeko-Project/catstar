package strategies

import (
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
)

type MockCommandFactory struct {
	mu             sync.Mutex
	Processes      []*MockProcess
	FailOnCreate   string
	CustomHandlers map[string]func(p *MockProcess) error
	OnCreate       func(p *MockProcess)
}

func NewMockCommandFactory() *MockCommandFactory {
	return &MockCommandFactory{
		CustomHandlers: make(map[string]func(p *MockProcess) error),
	}
}

func (m *MockCommandFactory) Create(ctx context.Context, name string, args ...string) Process {
	m.mu.Lock()
	defer m.mu.Unlock()

	fullCmd := name
	if len(args) > 0 {
		fullCmd = name + " " + strings.Join(args, " ")
	}

	p := &MockProcess{
		Name:    name,
		Args:    args,
		FullCmd: fullCmd,
		Env:     make([]string, 0),
	}

	if m.FailOnCreate != "" && name == m.FailOnCreate {
		p.FailOnStart = true
	}

	if m.CustomHandlers != nil {
		if handler, exists := m.CustomHandlers[name]; exists {
			p.RunFunc = handler
		}
	}

	if p.RunFunc == nil {
		p.RunFunc = func(proc *MockProcess) error {
			if proc.Stdin != nil {
				_, _ = io.Copy(io.Discard, proc.Stdin)
			}
			if proc.Name == "tar" {
				if proc.Stdout != nil {
					_, _ = proc.Stdout.Write([]byte("mock-tar-data"))
				}
			}
			if proc.Name == "openssl" {
				if proc.Stdout != nil {
					_, _ = proc.Stdout.Write([]byte("mock-tar-data-encrypted"))
				}
			}
			return nil
		}
	}

	if m.OnCreate != nil {
		m.OnCreate(p)
	}

	m.Processes = append(m.Processes, p)
	return p
}

type MockProcess struct {
	mu      sync.Mutex
	Name    string
	Args    []string
	FullCmd string
	Env     []string

	Stdin  io.Reader
	Stdout io.Writer
	Stderr io.Writer

	RunFunc func(p *MockProcess) error

	FailOnStart bool
	FailOnWait  bool

	errChan chan error
	started bool
	waited  bool
}

func (p *MockProcess) Start() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.started {
		return fmt.Errorf("mock process %s already started", p.Name)
	}
	p.started = true

	if p.FailOnStart {
		return fmt.Errorf("mock Start() failure for %s", p.Name)
	}

	p.errChan = make(chan error, 1)

	go func() {
		var err error
		if p.RunFunc != nil {
			err = p.RunFunc(p)
		}

		// Close PipeWriter to propagate EOF
		if pw, ok := p.Stdout.(*io.PipeWriter); ok {
			_ = pw.CloseWithError(err)
		}

		p.errChan <- err
	}()

	return nil
}

func (p *MockProcess) Wait() error {
	p.mu.Lock()
	if !p.started {
		p.mu.Unlock()
		return fmt.Errorf("mock process %s not started", p.Name)
	}
	if p.waited {
		p.mu.Unlock()
		return fmt.Errorf("mock process %s already waited", p.Name)
	}
	p.waited = true
	p.mu.Unlock()

	err := <-p.errChan
	if err == nil && p.FailOnWait {
		return fmt.Errorf("mock Wait() failure for %s", p.Name)
	}
	return err
}

func (p *MockProcess) StdoutPipe() (io.ReadCloser, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.started {
		return nil, fmt.Errorf("StdoutPipe called after process %s started", p.Name)
	}
	if p.Stdout != nil {
		return nil, fmt.Errorf("stdout already set for process %s", p.Name)
	}
	r, w := io.Pipe()
	p.Stdout = w
	return r, nil
}

func (p *MockProcess) StdinPipe() (io.WriteCloser, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.started {
		return nil, fmt.Errorf("StdinPipe called after process %s started", p.Name)
	}
	if p.Stdin != nil {
		return nil, fmt.Errorf("stdin already set for process %s", p.Name)
	}
	r, w := io.Pipe()
	p.Stdin = r
	return w, nil
}

func (p *MockProcess) SetStdin(r io.Reader) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.Stdin = r
}

func (p *MockProcess) SetStdout(w io.Writer) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.Stdout = w
}

func (p *MockProcess) SetStderr(w io.Writer) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.Stderr = w
}

func (p *MockProcess) SetEnv(env []string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.Env = env
}
