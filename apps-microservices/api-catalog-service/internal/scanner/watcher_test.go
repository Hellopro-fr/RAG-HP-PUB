package scanner

import (
	"context"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"
)

func TestWatchFile_TriggersOnWrite(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, ".env.url")
	if err := os.WriteFile(path, []byte("X=1\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var calls int32
	done := make(chan struct{})
	go func() {
		WatchFile(ctx, path, 50*time.Millisecond, func() { atomic.AddInt32(&calls, 1) })
		close(done)
	}()

	// Give the watcher time to register the dir.
	time.Sleep(100 * time.Millisecond)

	if err := os.WriteFile(path, []byte("X=2\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("X=3\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	// Wait past debounce window + slack.
	time.Sleep(250 * time.Millisecond)

	got := atomic.LoadInt32(&calls)
	if got != 1 {
		t.Fatalf("expected 1 debounced call, got %d", got)
	}

	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("watcher did not exit on cancel")
	}
}

func TestWatchFile_IgnoresUnrelatedFiles(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, ".env.url")
	other := filepath.Join(dir, "other.txt")
	if err := os.WriteFile(target, []byte("X=1\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var calls int32
	go WatchFile(ctx, target, 50*time.Millisecond, func() { atomic.AddInt32(&calls, 1) })
	time.Sleep(100 * time.Millisecond)

	if err := os.WriteFile(other, []byte("z"), 0o644); err != nil {
		t.Fatal(err)
	}
	time.Sleep(200 * time.Millisecond)

	if got := atomic.LoadInt32(&calls); got != 0 {
		t.Fatalf("unrelated file modified, expected 0 calls, got %d", got)
	}
}
