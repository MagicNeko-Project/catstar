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
	mutex     sync.RWMutex
	fixedTime time.Time
}

func NewMockClock(initialTime time.Time) *MockClock {
	return &MockClock{fixedTime: initialTime}
}

func (clock *MockClock) Now() time.Time {
	clock.mutex.RLock()
	defer clock.mutex.RUnlock()
	return clock.fixedTime
}

func (clock *MockClock) Set(newTime time.Time) {
	clock.mutex.Lock()
	defer clock.mutex.Unlock()
	clock.fixedTime = newTime
}

func (clock *MockClock) Advance(duration time.Duration) {
	clock.mutex.Lock()
	defer clock.mutex.Unlock()
	clock.fixedTime = clock.fixedTime.Add(duration)
}
