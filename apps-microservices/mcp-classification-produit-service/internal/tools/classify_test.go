package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"regexp"
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
	re := regexp.MustCompile(`^auto-[0-9a-f]{16}$`)
	if !re.MatchString(id) {
		t.Fatalf("expected forwarded id_produit to match %q, got %q", re.String(), id)
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

func TestHandleClassifyProductsBatch_AutoGeneratesMissingIDs(t *testing.T) {
	srv, captured := newStubBackend(t, "/classification/classify/batch", `{"resultats":[]}`)
	clients := &Clients{HTTP: srv.Client(), BaseURL: srv.URL}

	args := map[string]any{
		"produits": []any{
			map[string]any{
				"nom_produit": "A",
				"description": "desc-A",
			},
			map[string]any{
				"id_produit":  "SKU-B",
				"nom_produit": "B",
				"description": "desc-B",
			},
			map[string]any{
				"id_produit":  "",
				"nom_produit": "C",
				"description": "desc-C",
			},
		},
	}

	res, err := handleClassifyProductsBatch(context.Background(), clients, args)
	if err != nil {
		t.Fatalf("handler returned error: %v", err)
	}
	if res.IsError {
		t.Fatalf("expected success result, got error: %+v", res)
	}

	var sent struct {
		Produits []map[string]any `json:"produits"`
	}
	if err := json.Unmarshal(*captured, &sent); err != nil {
		t.Fatalf("unmarshal captured body: %v", err)
	}
	if len(sent.Produits) != 3 {
		t.Fatalf("expected 3 produits in payload, got %d", len(sent.Produits))
	}

	re := regexp.MustCompile(`^auto-[0-9a-f]{16}$`)

	// Item 0: missing id_produit → auto-generated.
	id0, _ := sent.Produits[0]["id_produit"].(string)
	if !re.MatchString(id0) {
		t.Fatalf("item 0: expected auto id, got %q", id0)
	}
	// Item 1: client-provided id_produit preserved.
	if id1, _ := sent.Produits[1]["id_produit"].(string); id1 != "SKU-B" {
		t.Fatalf("item 1: expected SKU-B, got %q", id1)
	}
	// Item 2: empty string → auto-generated.
	id2, _ := sent.Produits[2]["id_produit"].(string)
	if !re.MatchString(id2) {
		t.Fatalf("item 2: expected auto id, got %q", id2)
	}
	// And the two auto IDs must differ.
	if id0 == id2 {
		t.Fatalf("expected distinct auto ids, both were %q", id0)
	}
}

func TestHandleClassifyProductsBatch_EmptyProduits_ReturnsError(t *testing.T) {
	clients := &Clients{HTTP: http.DefaultClient, BaseURL: "http://unused.invalid"}
	args := map[string]any{"produits": []any{}}
	res, err := handleClassifyProductsBatch(context.Background(), clients, args)
	if err != nil {
		t.Fatalf("handler returned unexpected error: %v", err)
	}
	if !res.IsError {
		t.Fatalf("expected error result, got success: %+v", res)
	}
}

func TestHandleClassifyProductsBatch_MissingProduits_ReturnsError(t *testing.T) {
	clients := &Clients{HTTP: http.DefaultClient, BaseURL: "http://unused.invalid"}
	res, err := handleClassifyProductsBatch(context.Background(), clients, map[string]any{})
	if err != nil {
		t.Fatalf("handler returned unexpected error: %v", err)
	}
	if !res.IsError {
		t.Fatalf("expected error result, got success: %+v", res)
	}
}

func TestHandleClassifyProductsBatch_LeavesNonMapItemsUntouched(t *testing.T) {
	srv, captured := newStubBackend(t, "/classification/classify/batch", `{"resultats":[]}`)
	clients := &Clients{HTTP: srv.Client(), BaseURL: srv.URL}

	// Non-map items (e.g. a raw string) must pass through unchanged so the
	// backend can return its own structured per-item error.
	args := map[string]any{
		"produits": []any{"not-a-map"},
	}
	if _, err := handleClassifyProductsBatch(context.Background(), clients, args); err != nil {
		t.Fatalf("handler returned error: %v", err)
	}

	var sent struct {
		Produits []any `json:"produits"`
	}
	if err := json.Unmarshal(*captured, &sent); err != nil {
		t.Fatalf("unmarshal captured body: %v", err)
	}
	if len(sent.Produits) != 1 {
		t.Fatalf("expected 1 produit forwarded, got %d", len(sent.Produits))
	}
	if s, _ := sent.Produits[0].(string); s != "not-a-map" {
		t.Fatalf("expected non-map item to pass through as %q, got %v", "not-a-map", sent.Produits[0])
	}
}
