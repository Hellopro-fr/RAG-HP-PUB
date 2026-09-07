package tests

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/gorilla/websocket"
)

// setupAuditedServer monte le routeur complet avec un magasin d'audit
// enregistreur pour verifier que les actions destructrices sont tracees.
func setupAuditedServer(t *testing.T) (*httptest.Server, string, string, *recordingAudit) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	t.Cleanup(func() { _ = rs.Close() })
	base := t.TempDir()
	audit := &recordingAudit{}
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, FileStore: filestore.New(base), AuditStore: audit,
	}))
	t.Cleanup(srv.Close)
	return srv, base, mintToken("admin", "test-secret"), audit
}

// TestAudit_QueueMutationsAreLogged : drop / repair / clean-patterns et la
// deduplication de dataset doivent produire une entree d'audit.
func TestAudit_QueueMutationsAreLogged(t *testing.T) {
	srv, base, tok, audit := setupAuditedServer(t)
	jobID := "audited-job"
	writeQueueFile(t, base, jobID, "example.com", "0.json", "https://example.com/doc.pdf")

	if _, err := postJSON(srv.URL+"/api/jobs/"+jobID+"/request-queues/repair", tok, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := postJSON(srv.URL+"/api/jobs/"+jobID+"/request-queues/drop", tok, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := postJSON(srv.URL+"/api/jobs/"+jobID+"/request-queues/clean-patterns", tok, map[string]any{"patterns": []string{}}); err != nil {
		t.Fatal(err)
	}
	if _, err := postJSON(srv.URL+"/api/jobs/"+jobID+"/dataset/deduplicate", tok, nil); err != nil {
		t.Fatal(err)
	}

	want := map[string]bool{
		"repair_queues": false, "drop_queues": false,
		"clean_patterns": false, "dataset_deduplicate": false,
	}
	for _, e := range audit.Entries {
		a, _ := e["action"].(string)
		if _, tracked := want[a]; !tracked {
			continue
		}
		want[a] = true
		// L'identifiant de job doit accompagner l'action : sans lui,
		// l'audit dit qu'on a supprime des queues sans dire lesquelles.
		if e["target"] != jobID {
			t.Errorf("action %q: target = %v, want %q", a, e["target"], jobID)
		}
		md, ok := e["metadata"].(map[string]any)
		if !ok || md["id"] != jobID {
			t.Errorf("action %q: metadata = %v, want id=%q", a, e["metadata"], jobID)
		}
	}
	for action, seen := range want {
		if !seen {
			t.Errorf("action %q absente de l'audit (%d entrees)", action, len(audit.Entries))
		}
	}
}

// TestAudit_QueueFileWriteIsLogged : l'ecriture d'un fichier de queue est tracee.
func TestAudit_QueueFileWriteIsLogged(t *testing.T) {
	srv, base, tok, audit := setupAuditedServer(t)
	jobID := "audited-write-job"
	writeQueueFile(t, base, jobID, "example.com", "0.json", "https://example.com/p")

	body := bytes.NewReader([]byte(`{"id":"req_0","url":"https://example.com/p"}`))
	req, _ := http.NewRequest("POST", srv.URL+"/api/jobs/"+jobID+"/request-queues/example.com/0.json", body)
	req.Header.Set("Authorization", "Bearer "+tok)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	found := false
	for _, e := range audit.Entries {
		if e["action"] == "write_queue_file" {
			found = true
		}
	}
	if !found {
		t.Errorf("write_queue_file absente de l'audit (%d entrees)", len(audit.Entries))
	}
}

// TestQueues_CleanPatternsWithoutBody : corps vide accepte, patterns par defaut
// appliques (le PDF est supprime).
func TestQueues_CleanPatternsWithoutBody(t *testing.T) {
	srv, base, tok, _ := setupAuditedServer(t)
	jobID := "clean-default-job"
	writeQueueFile(t, base, jobID, "example.com", "0.json", "https://example.com/doc.pdf")
	writeQueueFile(t, base, jobID, "example.com", "1.json", "https://example.com/page")

	req, _ := http.NewRequest("POST", srv.URL+"/api/jobs/"+jobID+"/request-queues/clean-patterns", nil)
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
	if body["deleted"] != float64(1) {
		t.Errorf("deleted=%v want 1", body["deleted"])
	}
	if body["scanned"] != float64(2) {
		t.Errorf("scanned=%v want 2", body["scanned"])
	}
	remaining, _ := os.ReadDir(filepath.Join(base, jobID, "storage", "request_queues", "example.com"))
	if len(remaining) != 1 {
		t.Errorf("remaining=%d want 1", len(remaining))
	}
}

// TestCapacity_HistoryWindowValidation : 7d accepte, fenetre inconnue -> 400.
func TestCapacity_HistoryWindowValidation(t *testing.T) {
	srv, _, tok, _ := setupAuditedServer(t)

	resp, _ := authedGet(srv.URL+"/api/capacity/history?window=7d", tok)
	if resp.StatusCode != 200 {
		t.Errorf("window=7d -> status=%d, want 200", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["window"] != "7d" {
		t.Errorf("window=%v, want 7d", body["window"])
	}

	resp2, _ := authedGet(srv.URL+"/api/capacity/history?window=3h", tok)
	if resp2.StatusCode != 400 {
		t.Errorf("window=3h -> status=%d, want 400", resp2.StatusCode)
	}
}

// TestCallbacks_RetryFailureReturns200 : un webhook distant en erreur n'est pas
// une erreur de ce service — repondre 5xx ferait passer une panne tierce pour
// une panne du monitor.
func TestCallbacks_RetryFailureReturns200(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
	}))
	defer upstream.Close()

	srv, mr, tok := setupCallbacksServer(t)
	mr.Lpush(redisstore.FailedCallbacksKey, `{"url":"`+upstream.URL+`/hook","webhook_type":"on_finish","crawl_id":"job1","error":"timeout"}`)

	resp, err := postJSON(srv.URL+"/api/callbacks/0/retry", tok, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["success"] != false {
		t.Errorf("success=%v want false", body["success"])
	}
	if body["status"] != float64(500) {
		t.Errorf("status=%v want 500", body["status"])
	}
}

// TestWS_InvalidTokenClosesWith1008 : un token invalide n'est plus refuse avant
// l'upgrade (le navigateur ne voit pas le corps d'un 401 sur un handshake) mais
// ferme avec le code 1008 et la raison invalid_token.
func TestWS_InvalidTokenClosesWith1008(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())
	hub := ws.NewHub()
	defer hub.Close()
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}, Hub: hub,
	}))
	defer srv.Close()

	wsURL := strings.Replace(srv.URL, "http", "ws", 1) + "/?token=not.a.valid.token"
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, http.Header{})
	if err != nil {
		t.Fatalf("l'upgrade devait etre accepte: %v", err)
	}
	defer conn.Close()
	_, _, err = conn.ReadMessage()
	ce, ok := err.(*websocket.CloseError)
	if !ok {
		t.Fatalf("err = %v, want *websocket.CloseError", err)
	}
	if ce.Code != websocket.ClosePolicyViolation {
		t.Errorf("code = %d, want %d", ce.Code, websocket.ClosePolicyViolation)
	}
	if ce.Text != "invalid_token" {
		t.Errorf("reason = %q, want invalid_token", ce.Text)
	}
	if hub.Count() != 0 {
		t.Errorf("client enregistre malgre un token invalide: %d", hub.Count())
	}
}
