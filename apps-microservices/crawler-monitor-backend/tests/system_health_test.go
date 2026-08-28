package tests

import (
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
)

// setupHealthServer monte /api/system/health avec un compteur de crawls actifs
// et un pub/sub dont la fraicheur est pilotee par le test.
func setupHealthServer(t *testing.T, running string) (*httptest.Server, string, *ws.PubSub) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	if running != "" {
		mr.Set(redisstore.RunningCountKey, running)
	}
	rs, _ := redisstore.New("redis://" + mr.Addr())
	t.Cleanup(func() { _ = rs.Close() })
	hub := ws.NewHub()
	t.Cleanup(hub.Close)
	ps := ws.NewPubSub(rs, hub, "crawl_updates")
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
		Hub: hub, PubSub: ps,
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret"), ps
}

func healthBody(t *testing.T, srv *httptest.Server, tok string) map[string]any {
	t.Helper()
	resp, err := authedGet(srv.URL+"/api/system/health", tok)
	if err != nil {
		t.Fatal(err)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	return body
}

// TestSystemHealth_DegradedWhenPubSubStale : des crawls tournent, l'abonnement
// a bien vecu mais s'est taru depuis plus de 60 s (panne prod du 2026-08-28).
func TestSystemHealth_DegradedWhenPubSubStale(t *testing.T) {
	srv, tok, ps := setupHealthServer(t, "3")
	ps.SetLastMessageAtForTest(time.Now().Add(-2 * time.Minute).UnixMilli())

	body := healthBody(t, srv, tok)
	if body["status"] != "degraded" {
		t.Errorf("status = %v, want degraded (body=%v)", body["status"], body)
	}
	if age, _ := body["pubsub_last_message_age_ms"].(float64); age < 60000 {
		t.Errorf("pubsub_last_message_age_ms = %v, want > 60000", body["pubsub_last_message_age_ms"])
	}
	if body["running_count"] != float64(3) {
		t.Errorf("running_count = %v, want 3", body["running_count"])
	}
}

// TestSystemHealth_OkWhenPubSubFresh : des crawls tournent et les messages
// arrivent -> ok. Cas manquant : rien ne verifiait qu'un pub/sub sain ne
// declenchait pas l'alerte.
func TestSystemHealth_OkWhenPubSubFresh(t *testing.T) {
	srv, tok, ps := setupHealthServer(t, "3")
	ps.SetLastMessageAtForTest(time.Now().UnixMilli())

	body := healthBody(t, srv, tok)
	if body["status"] != "ok" {
		t.Errorf("status = %v, want ok (body=%v)", body["status"], body)
	}
	age, _ := body["pubsub_last_message_age_ms"].(float64)
	if age < 0 || age > 60000 {
		t.Errorf("pubsub_last_message_age_ms = %v, want 0..60000", age)
	}
}

// TestSystemHealth_NeverReceivedIsNotDegraded : au demarrage aucun message n'a
// encore transite ; l'age vaut -1 et le service n'est pas declare en panne.
func TestSystemHealth_NeverReceivedIsNotDegraded(t *testing.T) {
	srv, tok, _ := setupHealthServer(t, "3")

	body := healthBody(t, srv, tok)
	if body["status"] != "ok" {
		t.Errorf("status = %v, want ok (body=%v)", body["status"], body)
	}
	if body["pubsub_last_message_ms"] != float64(0) {
		t.Errorf("pubsub_last_message_ms = %v, want 0", body["pubsub_last_message_ms"])
	}
	if body["pubsub_last_message_age_ms"] != float64(-1) {
		t.Errorf("pubsub_last_message_age_ms = %v, want -1", body["pubsub_last_message_age_ms"])
	}
}

// TestSystemHealth_OkWhenIdle : sans crawl actif, le silence du pub/sub est normal.
func TestSystemHealth_OkWhenIdle(t *testing.T) {
	srv, tok, ps := setupHealthServer(t, "0")
	ps.SetLastMessageAtForTest(time.Now().Add(-time.Hour).UnixMilli())

	body := healthBody(t, srv, tok)
	if body["status"] != "ok" {
		t.Errorf("status = %v, want ok (body=%v)", body["status"], body)
	}
}
