package tests

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// seedCallbacks pousse N entrées JSON dans la liste Redis failed_callbacks.
func seedCallbacks(t *testing.T, mr *miniredis.Miniredis, count int) {
	t.Helper()
	for i := 0; i < count; i++ {
		entry := map[string]any{
			"url":          "https://api.example.com/hook",
			"params":       map[string]string{"crawl_id": "job1"},
			"webhook_type": "on_finish",
			"crawl_id":     "job1",
			"error":        "timeout",
		}
		b, _ := json.Marshal(entry)
		mr.Lpush(redisstore.FailedCallbacksKey, string(b))
	}
}

// setupCallbacksServer crée un serveur de test avec miniredis et FileStore minimal.
func setupCallbacksServer(t *testing.T) (*httptest.Server, *miniredis.Miniredis, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	t.Cleanup(func() { rs.Close() })
	fs := filestore.New(t.TempDir())
	audit := &recordingAudit{}
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, FileStore: fs, AuditStore: audit,
	}))
	t.Cleanup(srv.Close)
	return srv, mr, mintToken("admin", "test-secret")
}

// TestCallbacks_List vérifie que GET /api/callbacks retourne la liste avec count.
func TestCallbacks_List(t *testing.T) {
	srv, mr, tok := setupCallbacksServer(t)
	seedCallbacks(t, mr, 3)

	resp, err := authedGet(srv.URL+"/api/callbacks", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["count"] != float64(3) {
		t.Errorf("count=%v want 3", body["count"])
	}
	items, _ := body["items"].([]any)
	if len(items) != 3 {
		t.Errorf("items len=%d want 3", len(items))
	}
}

// TestCallbacks_ListEmpty vérifie que GET /api/callbacks retourne count=0 sur liste vide.
func TestCallbacks_ListEmpty(t *testing.T) {
	srv, _, tok := setupCallbacksServer(t)
	resp, _ := authedGet(srv.URL+"/api/callbacks", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["count"] != float64(0) {
		t.Errorf("count=%v want 0", body["count"])
	}
}

// TestCallbacks_DeleteOK vérifie que DELETE /api/callbacks/{idx} supprime l'entrée.
func TestCallbacks_DeleteOK(t *testing.T) {
	srv, mr, tok := setupCallbacksServer(t)
	seedCallbacks(t, mr, 2)

	req, _ := http.NewRequest("DELETE", srv.URL+"/api/callbacks/0", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != true {
		t.Errorf("deleted=%v want true", body["deleted"])
	}

	// Vérifie que la liste a maintenant 1 élément via re-list
	resp2, _ := authedGet(srv.URL+"/api/callbacks", tok)
	var body2 map[string]any
	decodeJSON(t, resp2.Body, &body2)
	if body2["count"] != float64(1) {
		t.Errorf("count after delete=%v want 1", body2["count"])
	}
}

// TestCallbacks_DeleteNotFound vérifie que DELETE /api/callbacks/{idx} sur index invalide retourne 404.
func TestCallbacks_DeleteNotFound(t *testing.T) {
	srv, _, tok := setupCallbacksServer(t)

	req, _ := http.NewRequest("DELETE", srv.URL+"/api/callbacks/99", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	resp, _ := http.DefaultClient.Do(req)
	if resp.StatusCode != 404 {
		t.Errorf("status=%d want 404", resp.StatusCode)
	}
}

// TestCallbacks_Clear vérifie que POST /api/callbacks/clear vide la liste.
func TestCallbacks_Clear(t *testing.T) {
	srv, mr, tok := setupCallbacksServer(t)
	seedCallbacks(t, mr, 5)

	resp, err := postJSON(srv.URL+"/api/callbacks/clear", tok, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["cleared"] != float64(5) {
		t.Errorf("cleared=%v want 5", body["cleared"])
	}

	// Vérifie que la liste est vide via re-list
	resp2, _ := authedGet(srv.URL+"/api/callbacks", tok)
	var body2 map[string]any
	decodeJSON(t, resp2.Body, &body2)
	if body2["count"] != float64(0) {
		t.Errorf("count after clear=%v want 0", body2["count"])
	}
}

// TestCallbacks_RetryNotFound vérifie que POST /api/callbacks/{idx}/retry sur index invalide retourne 404.
func TestCallbacks_RetryNotFound(t *testing.T) {
	srv, _, tok := setupCallbacksServer(t)
	resp, err := postJSON(srv.URL+"/api/callbacks/99/retry", tok, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 404 {
		t.Errorf("status=%d want 404", resp.StatusCode)
	}
}

// TestCallbacks_NoAuth vérifie que les routes callbacks exigent une authentification.
func TestCallbacks_NoAuth(t *testing.T) {
	srv, _, _ := setupCallbacksServer(t)
	resp, _ := http.Get(srv.URL + "/api/callbacks")
	if resp.StatusCode != 401 {
		t.Errorf("status=%d want 401", resp.StatusCode)
	}
}
