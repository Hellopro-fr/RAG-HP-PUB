package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// recordingAuditAlbums captures all audit Append calls (separate from helpers_test
// recordingAudit to avoid type confusion in mixed test runs).
type recordingAuditAlbums struct {
	mu      sync.Mutex
	Entries []map[string]any
}

func (r *recordingAuditAlbums) Append(_ context.Context, e map[string]any) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.Entries = append(r.Entries, e)
	return nil
}

func (r *recordingAuditAlbums) all() []map[string]any {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]map[string]any, len(r.Entries))
	copy(out, r.Entries)
	return out
}

// upstream stub that records every call.
type upstreamSpy struct {
	mu       sync.Mutex
	URLs     []string
	Methods  []string
	Bodies   []string
	respond  func(w http.ResponseWriter, r *http.Request)
	count    atomic.Int64
}

func newUpstreamSpy(respond func(http.ResponseWriter, *http.Request)) (*httptest.Server, *upstreamSpy) {
	spy := &upstreamSpy{respond: respond}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		spy.count.Add(1)
		body, _ := io.ReadAll(r.Body)
		spy.mu.Lock()
		spy.URLs = append(spy.URLs, r.URL.RequestURI())
		spy.Methods = append(spy.Methods, r.Method)
		spy.Bodies = append(spy.Bodies, string(body))
		spy.mu.Unlock()
		spy.respond(w, r)
	}))
	return srv, spy
}

func setupAlbumsTest(t *testing.T, audit httpapi.AuditAppender, upstream *httptest.Server) (*httptest.Server, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	t.Setenv("IMAGE_DOWNLOAD_SERVICE_URL", upstream.URL)
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: audit,
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret")
}

func TestAlbums_GET_RequiresJWT(t *testing.T) {
	upstream, _ := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) })
	defer upstream.Close()
	srv, _ := setupAlbumsTest(t, &recordingAuditAlbums{}, upstream)
	resp, _ := http.Get(srv.URL + "/api/albums/")
	if resp.StatusCode != 401 {
		t.Errorf("status=%d, want 401", resp.StatusCode)
	}
}

func TestAlbums_GET_ForwardsSummary(t *testing.T) {
	upstream, spy := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[{"domain":"example.com","images":42}]`))
	})
	defer upstream.Close()
	srv, tok := setupAlbumsTest(t, &recordingAuditAlbums{}, upstream)
	resp, err := authedGet(srv.URL+"/api/albums/", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	if len(spy.URLs) != 1 || !strings.HasSuffix(spy.URLs[0], "/domains/_summary") {
		t.Errorf("upstream URL=%v", spy.URLs)
	}
	if spy.Methods[0] != "GET" {
		t.Errorf("method=%s", spy.Methods[0])
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "example.com") {
		t.Errorf("body=%s", body)
	}
}

func TestAlbums_GET_ForwardsQueryString(t *testing.T) {
	upstream, spy := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"items":[],"total":0}`))
	})
	defer upstream.Close()
	srv, tok := setupAlbumsTest(t, &recordingAuditAlbums{}, upstream)
	_, err := authedGet(srv.URL+"/api/albums/example.com/products?page=2&limit=50&search=foo", tok)
	if err != nil {
		t.Fatal(err)
	}
	if len(spy.URLs) != 1 {
		t.Fatalf("upstream calls=%d", len(spy.URLs))
	}
	got := spy.URLs[0]
	for _, want := range []string{"/domains/example.com/products", "page=2", "limit=50", "search=foo"} {
		if !strings.Contains(got, want) {
			t.Errorf("URL %q missing %q", got, want)
		}
	}
}

func TestAlbums_DELETE_204Propagated(t *testing.T) {
	upstream, spy := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) })
	defer upstream.Close()
	audit := &recordingAuditAlbums{}
	srv, tok := setupAlbumsTest(t, audit, upstream)

	req, _ := http.NewRequest("DELETE", srv.URL+"/api/albums/example.com/products/abc123/images/img-001.jpg", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 204 {
		t.Errorf("status=%d, want 204", resp.StatusCode)
	}
	if len(spy.URLs) != 1 || !strings.HasSuffix(spy.URLs[0], "/images/example.com/abc123/img-001.jpg") {
		t.Errorf("upstream URL=%v", spy.URLs)
	}
	if spy.Methods[0] != "DELETE" {
		t.Errorf("method=%s", spy.Methods[0])
	}
	entries := audit.all()
	if len(entries) != 1 || entries[0]["action"] != "delete_image" {
		t.Errorf("audit entries=%v", entries)
	}
}

func TestAlbums_POST_ForwardsBody(t *testing.T) {
	upstream, spy := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(202)
		_, _ = w.Write([]byte(`{"job_id":"sync-uuid"}`))
	})
	defer upstream.Close()
	audit := &recordingAuditAlbums{}
	srv, tok := setupAlbumsTest(t, audit, upstream)

	req, _ := http.NewRequest("POST", srv.URL+"/api/albums/example.com/sync", bytes.NewBufferString(`{"force":true}`))
	req.Header.Set("Authorization", "Bearer "+tok)
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 202 {
		t.Errorf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&body)
	if body["job_id"] != "sync-uuid" {
		t.Errorf("body=%v", body)
	}
	if len(spy.URLs) != 1 || !strings.HasSuffix(spy.URLs[0], "/sync/example.com") {
		t.Errorf("upstream URL=%v", spy.URLs)
	}
	if spy.Bodies[0] != `{"force":true}` {
		t.Errorf("body forwarded=%s", spy.Bodies[0])
	}
	if !auditHasAction(audit.all(), "sync_album") {
		t.Error("audit action sync_album missing")
	}
}

func TestAlbums_RateLimit_11thDeleteRejected(t *testing.T) {
	upstream, _ := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) })
	defer upstream.Close()
	srv, tok := setupAlbumsTest(t, &recordingAuditAlbums{}, upstream)

	for i := 0; i < 10; i++ {
		req, _ := http.NewRequest("DELETE", srv.URL+"/api/albums/example.com/products/p"+strconvI(i), nil)
		req.Header.Set("Authorization", "Bearer "+tok)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		if resp.StatusCode != 204 {
			t.Errorf("call #%d: status=%d", i, resp.StatusCode)
		}
		resp.Body.Close()
	}
	req, _ := http.NewRequest("DELETE", srv.URL+"/api/albums/example.com/products/p11", nil)
	req.Header.Set("Authorization", "Bearer "+tok)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 429 {
		t.Errorf("11th call: status=%d, want 429", resp.StatusCode)
	}
}

func TestAlbums_GETs_NotRateLimited(t *testing.T) {
	upstream, _ := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[]`))
	})
	defer upstream.Close()
	srv, tok := setupAlbumsTest(t, &recordingAuditAlbums{}, upstream)

	for i := 0; i < 20; i++ {
		resp, err := authedGet(srv.URL+"/api/albums/", tok)
		if err != nil {
			t.Fatal(err)
		}
		if resp.StatusCode != 200 {
			t.Errorf("GET #%d: status=%d", i+1, resp.StatusCode)
		}
		resp.Body.Close()
	}
}

func TestAlbums_DestructiveAuditCoverage(t *testing.T) {
	upstream, _ := newUpstreamSpy(func(w http.ResponseWriter, r *http.Request) {
		// Some routes return 202, others 204. Either is fine for audit purposes.
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(202)
		_, _ = w.Write([]byte(`{}`))
	})
	defer upstream.Close()
	audit := &recordingAuditAlbums{}
	srv, tok := setupAlbumsTest(t, audit, upstream)

	calls := []struct {
		method, path, want string
	}{
		{"POST", "/api/albums/d.com/sync", "sync_album"},
		{"POST", "/api/albums/d.com/products/p1/redownload", "redownload_product"},
		{"POST", "/api/albums/d.com/products/p1/images/i1.jpg/redownload", "redownload_image"},
		{"DELETE", "/api/albums/d.com", "delete_album"},
		{"DELETE", "/api/albums/d.com/products/p1", "delete_product"},
		{"DELETE", "/api/albums/d.com/products/p1/images/i1.jpg", "delete_image"},
	}
	for _, c := range calls {
		req, _ := http.NewRequest(c.method, srv.URL+c.path, nil)
		req.Header.Set("Authorization", "Bearer "+tok)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
	}
	for _, c := range calls {
		if !auditHasAction(audit.all(), c.want) {
			t.Errorf("missing audit action %q", c.want)
		}
	}
}

func auditHasAction(entries []map[string]any, action string) bool {
	for _, e := range entries {
		if e["action"] == action {
			return true
		}
	}
	return false
}

func strconvI(i int) string {
	if i < 10 {
		return string(rune('0' + i))
	}
	return string(rune('0'+i/10)) + string(rune('0'+i%10))
}
