package health

import (
	"testing"
	"time"
)

func TestNewChecker(t *testing.T) {
	c := NewChecker(nil, nil, nil, 30*time.Second, nil)
	if c == nil {
		t.Fatal("expected non-nil checker")
	}
	if c.interval != 30*time.Second {
		t.Errorf("expected 30s interval, got %s", c.interval)
	}
}
