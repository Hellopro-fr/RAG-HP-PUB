package tests

import (
	"encoding/json"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// jobWithSecrets : job tel qu'ecrit par crawler-service, avec secrets,
// chemins serveur et dates naives.
const jobWithSecrets = `{
  "crawl_id":"abc","domain":"example.com","status":"running",
  "start_time":"2026-08-28 13:20:03.306901",
  "finished_at":"2026-08-28 14:00:00.000000",
  "last_heartbeat":"2026-08-28 13:59:00.000000",
  "pid":4242,
  "storage_path":"/app/storage/abc",
  "start_url":"https://example.com/",
  "callback_url":"https://api.hellopro.eu/hook?token=SECRET",
  "failure_callback_url":"https://api.hellopro.eu/fail?token=SECRET",
  "terminal_webhook_request_id":"req-9",
  "params":{"proxyapify":"SECRET","apifyToken":"SECRET","crawlMode":"update",
            "maxCrawlDepth":3,"maxConcurrency":8,"camoufox":true}
}`

func setupRedactionTest(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	mr.Set("crawl_job:abc", jobWithSecrets)
	mr.Set("crawl_job:old", `{"id":"old","status":"finished","start_time":"2020-01-01T00:00:00Z"}`)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret")
}

// TestJobs_ListRedactsSecrets : ni la liste ni le detail ne doivent laisser
// fuiter le token proxy/apify ou les chemins serveur.
func TestJobs_ListRedactsSecrets(t *testing.T) {
	srv, tok := setupRedactionTest(t)
	for _, path := range []string{"/api/jobs", "/api/jobs/abc/details"} {
		resp, err := authedGet(srv.URL+path, tok)
		if err != nil {
			t.Fatal(err)
		}
		b, _ := io.ReadAll(resp.Body)
		body := string(b)
		if resp.StatusCode != 200 {
			t.Fatalf("%s status=%d body=%s", path, resp.StatusCode, body)
		}
		for _, forbidden := range []string{"SECRET", "storage_path", "start_url", `"pid"`, "_redisKey", `"params"`} {
			if strings.Contains(body, forbidden) {
				t.Errorf("%s expose %q", path, forbidden)
			}
		}
	}
}

// TestJobs_DetailsConfigAndCallback : le detail expose une vue config
// (allowlist, renommee) et un resume callback sans query string.
func TestJobs_DetailsConfigAndCallback(t *testing.T) {
	srv, tok := setupRedactionTest(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/abc/details", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	cfg, _ := body["config"].(map[string]any)
	if cfg["strategy"] != "update" {
		t.Errorf("config.strategy = %v, want update", cfg["strategy"])
	}
	if cfg["depth"] != float64(3) {
		t.Errorf("config.depth = %v, want 3", cfg["depth"])
	}
	if cfg["concurrency"] != float64(8) {
		t.Errorf("config.concurrency = %v, want 8", cfg["concurrency"])
	}
	if cfg["camoufox"] != true {
		t.Errorf("config.camoufox = %v, want true", cfg["camoufox"])
	}
	if _, ok := cfg["proxyapify"]; ok {
		t.Error("config expose proxyapify")
	}
	if _, ok := cfg["apifyToken"]; ok {
		t.Error("config expose apifyToken")
	}

	cb, _ := body["callback"].(map[string]any)
	if cb["url"] != "https://api.hellopro.eu/hook" {
		t.Errorf("callback.url = %v", cb["url"])
	}
	if cb["failure_url"] != "https://api.hellopro.eu/fail" {
		t.Errorf("callback.failure_url = %v", cb["failure_url"])
	}
	if cb["status"] != "sent" {
		t.Errorf("callback.status = %v, want sent", cb["status"])
	}
}

// TestJobs_DatesNormalizedToUTC : les dates naives de crawler-service sont
// renvoyees en RFC3339 UTC.
func TestJobs_DatesNormalizedToUTC(t *testing.T) {
	srv, tok := setupRedactionTest(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/abc/details", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	cases := map[string]string{
		"start_time":     "2026-08-28T13:20:03.306Z",
		"finished_at":    "2026-08-28T14:00:00Z",
		"last_heartbeat": "2026-08-28T13:59:00Z",
	}
	for field, want := range cases {
		got, _ := body[field].(string)
		if got != want {
			t.Errorf("%s = %q, want %q", field, got, want)
		}
	}
}

// TestJobs_ListFilters : ?status= et ?window= filtrent cote serveur sans
// changer la forme de la reponse (tableau).
func TestJobs_ListFilters(t *testing.T) {
	srv, tok := setupRedactionTest(t)

	resp, _ := authedGet(srv.URL+"/api/jobs?status=running", tok)
	var jobs []map[string]any
	decodeJSON(t, resp.Body, &jobs)
	if len(jobs) != 1 || jobs[0]["id"] != "abc" {
		t.Errorf("status=running -> %v", jobs)
	}

	// Fenetre 15m : le job de 2020 doit disparaitre.
	resp2, _ := authedGet(srv.URL+"/api/jobs?window=30d", tok)
	var jobs2 []map[string]any
	decodeJSON(t, resp2.Body, &jobs2)
	for _, j := range jobs2 {
		if j["id"] == "old" {
			t.Error("le job de 2020 ne devrait pas passer la fenetre 30d")
		}
	}

	resp3, _ := authedGet(srv.URL+"/api/jobs?window=42y", tok)
	if resp3.StatusCode != 400 {
		t.Errorf("window invalide -> status=%d, want 400", resp3.StatusCode)
	}
}

// TestDomains_TotalJobs : la liste des domaines expose total_jobs (somme) et
// conserve count (nombre de domaines).
func TestDomains_TotalJobs(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	mr.Set("crawl_job:a1", `{"id":"a1","domain":"a.com","status":"finished","start_time":"`+isoNow()+`"}`)
	mr.Set("crawl_job:a2", `{"id":"a2","domain":"a.com","status":"finished","start_time":"`+isoNow()+`"}`)
	mr.Set("crawl_job:b1", `{"id":"b1","domain":"b.com","status":"finished","start_time":"`+isoNow()+`"}`)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	defer srv.Close()

	resp, _ := authedGet(srv.URL+"/api/domains?window=7d", mintToken("admin", "test-secret"))
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["count"] != float64(2) {
		t.Errorf("count = %v, want 2", body["count"])
	}
	if body["total_jobs"] != float64(3) {
		t.Errorf("total_jobs = %v, want 3", body["total_jobs"])
	}
}

// TestJobs_CallbackStatusNoneWhenUnconfigured : sans aucun webhook configure,
// "pending" laissait le dashboard attendre un envoi qui n'arrivera jamais.
func TestJobs_CallbackStatusNoneWhenUnconfigured(t *testing.T) {
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	mr.Set("crawl_job:nocb", `{"id":"nocb","status":"finished","start_time":"2026-08-28T10:00:00Z"}`)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)

	resp, err := authedGet(srv.URL+"/api/jobs/nocb/details", mintToken("admin", "test-secret"))
	if err != nil {
		t.Fatal(err)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	cb, _ := body["callback"].(map[string]any)
	if cb["status"] != "none" {
		t.Errorf("callback.status = %v, want none", cb["status"])
	}
}
