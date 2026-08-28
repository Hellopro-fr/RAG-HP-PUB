package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/go-chi/chi/v5"
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

// TestAudit_CaptureParams : les parametres de route alimentent metadata, et
// "id" devient la cible de l'entree d'audit.
func TestAudit_CaptureParams(t *testing.T) {
	store := &fakeAuditStore{}
	mw := AuditMiddleware(store, "drop_queues", AuditOptions{
		CaptureParams: []string{"id", "domain", "filename"},
	})
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))

	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("id", "job-42")
	rctx.URLParams.Add("domain", "example.com")
	r := httptest.NewRequest("POST", "/x", nil).
		WithContext(context.WithValue(context.Background(), chi.RouteCtxKey, rctx))
	h.ServeHTTP(httptest.NewRecorder(), r)

	e := store.entries[0]
	if e["target"] != "job-42" {
		t.Errorf("target = %v, want job-42", e["target"])
	}
	md, ok := e["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("metadata missing/wrong type: %T", e["metadata"])
	}
	if md["id"] != "job-42" || md["domain"] != "example.com" {
		t.Errorf("metadata = %v", md)
	}
	if _, exists := md["filename"]; exists {
		t.Error("filename absent de la route ne doit pas etre capture")
	}
}
