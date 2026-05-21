package clock

import (
	"sync"
	"time"
)

type Provider interface {
	Now() time.Time
}

type RealClock struct{}

func NewRealClock() *RealClock {
	return &RealClock{}
}

func (RealClock) Now() time.Time {
	return time.Now()
}

type MockClock struct {
	mu        sync.RWMutex
	fixedTime time.Time
}

func NewMockClock(t time.Time) *MockClock {
	return &MockClock{fixedTime: t}
}

func (m *MockClock) Now() time.Time {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.fixedTime
}

func (m *MockClock) Set(t time.Time) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.fixedTime = t
}

func (m *MockClock) Advance(d time.Duration) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.fixedTime = m.fixedTime.Add(d)
}
