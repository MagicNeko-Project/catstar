package strategies

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"
	"sync"
)

// MockCommandFactory instantiates mock processes for testing pipelines.
type MockCommandFactory struct {
	mu           sync.Mutex
	Processes    []*MockProcess
	FailOnCreate string // E.g., "tar" to fail process creation
}

func (m *MockCommandFactory) Create(ctx context.Context, name string, args ...string) Process {
	m.mu.Lock()
	defer m.mu.Unlock()
	
	fullCmd := name + " " + strings.Join(args, " ")
	
	p := &MockProcess{
		Name:     name,
		FullCmd:  fullCmd,
		Env:      make([]string, 0),
		inBuf:    &bytes.Buffer{},
		outBuf:   &bytes.Buffer{},
	}
	
	if m.FailOnCreate != "" && name == m.FailOnCreate {
		p.FailOnStart = true
	}
	
	m.Processes = append(m.Processes, p)
	return p
}

// MockProcess simulates a running process with connected I/O pipes.
type MockProcess struct {
	Name    string
	FullCmd string
	Env     []string

	Stdin  io.Reader
	Stdout io.Writer
	Stderr io.Writer

	inBuf  *bytes.Buffer
	outBuf *bytes.Buffer

	FailOnStart bool
	FailOnWait  bool
	
	Started bool
	Waited  bool
}

func (p *MockProcess) Start() error {
	p.Started = true
	if p.FailOnStart {
		return fmt.Errorf("mock Start() failure for %s", p.Name)
	}
	return nil
}

func (p *MockProcess) Wait() error {
	p.Waited = true
	if p.FailOnWait {
		return fmt.Errorf("mock Wait() failure for %s", p.Name)
	}

	// Simulate data processing during Wait() so pipeline executes sequentially 
	// based on the way errgroup handles them.
	if p.Stdin != nil {
		data, _ := io.ReadAll(p.Stdin)
		p.inBuf.Write(data)
	}

	if p.Name == "openssl" {
		p.outBuf.WriteString(p.inBuf.String() + "-encrypted")
	}

	if p.Name == "tar" {
		p.outBuf.WriteString("mock-tar-data")
	}

	if p.Stdout != nil {
		p.Stdout.Write(p.outBuf.Bytes())
	}

	return nil
}

func (p *MockProcess) StdoutPipe() (io.ReadCloser, error) {
	// Expose the outBuf to be read by the next process
	return io.NopCloser(p.outBuf), nil
}

func (p *MockProcess) StdinPipe() (io.WriteCloser, error) {
	return nil, fmt.Errorf("not implemented in mock")
}

func (p *MockProcess) SetStdin(r io.Reader) { p.Stdin = r }
func (p *MockProcess) SetStdout(w io.Writer) { p.Stdout = w }
func (p *MockProcess) SetStderr(w io.Writer) { p.Stderr = w }
func (p *MockProcess) SetEnv(env []string) { p.Env = env }

