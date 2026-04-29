package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
)

type fakeAuditStore struct {
	mu      sync.Mutex
	entries []map[string]any
}

func (f *fakeAuditStore) Append(ctx context.Context, e map[string]any) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.entries = append(f.entries, e)
	return nil
}

func TestAudit_BasicCapture(t *testing.T) {
	store := &fakeAuditStore{}
	mw := AuditMiddleware(store, "test_action", AuditOptions{})
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	r := httptest.NewRequest("GET", "/x", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if len(store.entries) != 1 {
		t.Fatalf("entries = %d, want 1", len(store.entries))
	}
	e := store.entries[0]
	if e["action"] != "test_action" {
		t.Errorf("action = %v", e["action"])
	}
	if e["status"] != "ok" {
		t.Errorf("status = %v, want ok (200)", e["status"])
	}
}

func TestAudit_StatusErrorOn4xx(t *testing.T) {
	store := &fakeAuditStore{}
	mw := AuditMiddleware(store, "x", AuditOptions{})
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(400)
	}))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	h.ServeHTTP(w, r)
	if store.entries[0]["status"] != "error" {
		t.Errorf("status = %v, want error", store.entries[0]["status"])
	}
}

func TestAudit_CaptureQuery(t *testing.T) {
	store := &fakeAuditStore{}
	mw := AuditMiddleware(store, "x", AuditOptions{CaptureQuery: []string{"id", "domain"}})
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	r := httptest.NewRequest("GET", "/x?id=42&domain=example.com&hidden=secret", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	md, ok := store.entries[0]["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("metadata missing/wrong type: %T", store.entries[0]["metadata"])
	}
	if md["id"] != "42" || md["domain"] != "example.com" {
		t.Errorf("metadata = %v", md)
	}
	if _, exists := md["hidden"]; exists {
		t.Error("hidden field should not be captured")
	}
}
