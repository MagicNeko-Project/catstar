package clock

import "time"

// Provider allows injecting deterministic time into the application
// for robust unit testing of time-based logic (e.g., summary windows).
type Provider interface {
	Now() time.Time
}

// RealClock returns the actual system time.
type RealClock struct{}

// NewRealClock instantiates a clock bound to the host OS.
func NewRealClock() *RealClock {
	return &RealClock{}
}

// Now returns the current wall-clock time.
func (RealClock) Now() time.Time {
	return time.Now()
}

// MockClock returns a predefined, frozen time.
type MockClock struct {
	FixedTime time.Time
}

// NewMockClock instantiates a clock frozen at the given instant.
func NewMockClock(t time.Time) *MockClock {
	return &MockClock{FixedTime: t}
}

// Now returns the frozen time.
func (m *MockClock) Now() time.Time {
	return m.FixedTime
}
