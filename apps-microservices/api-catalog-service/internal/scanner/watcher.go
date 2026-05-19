package scanner

import (
	"context"
	"log"
	"path/filepath"
	"time"

	"github.com/fsnotify/fsnotify"
)

// WatchFile triggers onChange whenever the given file is written or replaced.
// Watches the parent directory because editors and bind-mount writers often
// use rename-then-replace, which breaks a watch on the file itself.
//
// Multiple events from a single save are coalesced via debounce.
// Returns when ctx is cancelled.
func WatchFile(ctx context.Context, path string, debounce time.Duration, onChange func()) {
	dir := filepath.Dir(path)
	target := filepath.Clean(path)

	w, err := fsnotify.NewWatcher()
	if err != nil {
		log.Printf("watcher: NewWatcher failed: %v", err)
		return
	}
	defer w.Close()

	if err := w.Add(dir); err != nil {
		log.Printf("watcher: cannot watch %s: %v", dir, err)
		return
	}
	log.Printf("watcher: watching %s for changes", target)

	var timer *time.Timer
	fire := func() {
		log.Printf("watcher: %s changed, triggering scan", target)
		onChange()
	}

	for {
		select {
		case <-ctx.Done():
			return
		case ev, ok := <-w.Events:
			if !ok {
				return
			}
			if filepath.Clean(ev.Name) != target {
				continue
			}
			if ev.Op&(fsnotify.Write|fsnotify.Create|fsnotify.Rename) == 0 {
				continue
			}
			if timer != nil {
				timer.Stop()
			}
			timer = time.AfterFunc(debounce, fire)
		case err, ok := <-w.Errors:
			if !ok {
				return
			}
			log.Printf("watcher: error: %v", err)
		}
	}
}
