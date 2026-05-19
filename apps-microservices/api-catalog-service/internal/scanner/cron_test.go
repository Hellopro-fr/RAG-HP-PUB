package scanner

import (
	"context"
	"testing"
	"time"
)

func TestRunCron_StopsOnContextCancel(t *testing.T) {
	// Verify RunCron returns when context is cancelled without blocking.
	ctx, cancel := context.WithCancel(context.Background())

	// Use a very long interval so the ticker never fires; we only test cancellation.
	done := make(chan struct{})
	go func() {
		RunCron(ctx, nil, 10*time.Minute, func() map[string]string { return nil })
		close(done)
	}()

	cancel()
	select {
	case <-done:
		// expected
	case <-time.After(2 * time.Second):
		t.Fatal("RunCron did not stop after context cancellation")
	}
}
