package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"
)

// newStubBackend spins up an httptest server that records the last request body
// received at the given path and returns the provided response body.
func newStubBackend(t *testing.T, wantPath string, response string) (*httptest.Server, *[]byte) {
	t.Helper()
	var captured []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != wantPath {
			t.Errorf("unexpected path: got %q, want %q", r.URL.Path, wantPath)
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("read request body: %v", err)
		}
		captured = body
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(response))
	}))
	t.Cleanup(srv.Close)
	return srv, &captured
}

func TestHandleClassifyProduct_MissingIDProduit_GeneratesAutoID(t *testing.T) {
	srv, captured := newStubBackend(t, "/classification/classify", `{"ok":true}`)
	clients := &Clients{HTTP: srv.Client(), BaseURL: srv.URL}

	args := map[string]any{
		"nom_produit": "Perceuse Bosch",
		"description": "Perceuse 750W",
	}
	res, err := handleClassifyProduct(context.Background(), clients, args)
	if err != nil {
		t.Fatalf("handler returned error: %v", err)
	}
	if res.IsError {
		t.Fatalf("expected success result, got error: %+v", res)
	}

	var sent map[string]any
	if err := json.Unmarshal(*captured, &sent); err != nil {
		t.Fatalf("unmarshal captured body: %v", err)
	}
	id, _ := sent["id_produit"].(string)
	re := regexp.MustCompile(`^auto-[0-9a-f]{16}$`)
	if !re.MatchString(id) {
		t.Fatalf("expected forwarded id_produit to match %q, got %q", re.String(), id)
	}
}

func TestHandleClassifyProduct_EmptyIDProduit_GeneratesAutoID(t *testing.T) {
	srv, captured := newStubBackend(t, "/classification/classify", `{"ok":true}`)
	clients := &Clients{HTTP: srv.Client(), BaseURL: srv.URL}

	args := map[string]any{
		"id_produit":  "",
		"nom_produit": "Perceuse Bosch",
		"description": "Perceuse 750W",
	}
	if _, err := handleClassifyProduct(context.Background(), clients, args); err != nil {
		t.Fatalf("handler returned error: %v", err)
	}

	var sent map[string]any
	if err := json.Unmarshal(*captured, &sent); err != nil {
		t.Fatalf("unmarshal captured body: %v", err)
	}
	id, _ := sent["id_produit"].(string)
	if !strings.HasPrefix(id, "auto-") {
		t.Fatalf("expected auto-generated id, got %q", id)
	}
}

func TestHandleClassifyProduct_ClientProvidedIDPassesThrough(t *testing.T) {
	srv, captured := newStubBackend(t, "/classification/classify", `{"ok":true}`)
	clients := &Clients{HTTP: srv.Client(), BaseURL: srv.URL}

	args := map[string]any{
		"id_produit":  "SKU-42",
		"nom_produit": "Perceuse Bosch",
		"description": "Perceuse 750W",
	}
	if _, err := handleClassifyProduct(context.Background(), clients, args); err != nil {
		t.Fatalf("handler returned error: %v", err)
	}

	var sent map[string]any
	if err := json.Unmarshal(*captured, &sent); err != nil {
		t.Fatalf("unmarshal captured body: %v", err)
	}
	if id, _ := sent["id_produit"].(string); id != "SKU-42" {
		t.Fatalf("expected id_produit=SKU-42, got %q", id)
	}
}

func TestHandleClassifyProduct_MissingNomProduit_ReturnsError(t *testing.T) {
	// No stub server needed — handler must reject before reaching backend.
	clients := &Clients{HTTP: http.DefaultClient, BaseURL: "http://unused.invalid"}
	args := map[string]any{"description": "x"}
	res, err := handleClassifyProduct(context.Background(), clients, args)
	if err != nil {
		t.Fatalf("handler returned unexpected error: %v", err)
	}
	if !res.IsError {
		t.Fatalf("expected error result, got success: %+v", res)
	}
}

func TestHandleClassifyProduct_MissingDescription_ReturnsError(t *testing.T) {
	clients := &Clients{HTTP: http.DefaultClient, BaseURL: "http://unused.invalid"}
	args := map[string]any{"nom_produit": "x"}
	res, err := handleClassifyProduct(context.Background(), clients, args)
	if err != nil {
		t.Fatalf("handler returned unexpected error: %v", err)
	}
	if !res.IsError {
		t.Fatalf("expected error result, got success: %+v", res)
	}
}
