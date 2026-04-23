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

func TestRecordDown_FirstStampWins(t *testing.T) {
	c := NewChecker(nil, nil, nil, 30*time.Second, nil)
	c.recordDown("server-1")
	first, ok := c.downSince["server-1"]
	if !ok {
		t.Fatal("expected downSince entry after recordDown")
	}
	// Re-recording should NOT overwrite: idempotent so flapping during the
	// same outage keeps the original downtime start.
	time.Sleep(5 * time.Millisecond)
	c.recordDown("server-1")
	if !c.downSince["server-1"].Equal(first) {
		t.Error("recordDown should be idempotent — existing timestamp must not be overwritten")
	}
}

func TestClearDown_ReturnsDurationAndRemoves(t *testing.T) {
	c := NewChecker(nil, nil, nil, 30*time.Second, nil)
	c.recordDown("server-1")
	time.Sleep(5 * time.Millisecond)
	dur := c.clearDown("server-1")
	if dur <= 0 {
		t.Errorf("expected positive duration, got %s", dur)
	}
	if _, ok := c.downSince["server-1"]; ok {
		t.Error("clearDown should remove the entry")
	}
	if c.clearDown("server-1") != 0 {
		t.Error("clearDown on missing id should return 0")
	}
}
