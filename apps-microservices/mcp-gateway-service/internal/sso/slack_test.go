package sso

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestSlackNotifier_Post(t *testing.T) {
	var hits atomic.Int32
	var lastBody []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		b, _ := io.ReadAll(r.Body)
		lastBody = b
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	n := NewSlackNotifier(srv.URL, "test-env", "https://gw.example")
	n.Notify(SSOErrorEvent{
		Kind:     "state_mismatch",
		Reason:   "query state did not match pending",
		ClientIP: "1.2.3.4",
	})
	// Notify is non-blocking — wait briefly for the goroutine.
	time.Sleep(150 * time.Millisecond)
	if hits.Load() != 1 {
		t.Fatalf("expected 1 hit, got %d", hits.Load())
	}
	var payload map[string]any
	if err := json.Unmarshal(lastBody, &payload); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, ok := payload["text"]; !ok {
		t.Fatal("missing text field")
	}
}

func TestSlackNotifier_Disabled(t *testing.T) {
	n := NewSlackNotifier("", "", "")
	// Must not panic, must not block.
	n.Notify(SSOErrorEvent{Kind: "x"})
}
