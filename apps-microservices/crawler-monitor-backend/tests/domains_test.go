package tests

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/domains"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// ---------------------------------------------------------------------------
// Unit tests — pure domain logic
// ---------------------------------------------------------------------------

// TestDomainsParseDomainWindow_Accepts mirrors "parseDomainWindow accepts 24h, 7d, 30d".
func TestDomainsParseDomainWindow_Accepts(t *testing.T) {
	cases := map[string]int64{
		"24h": 24 * 60 * 60 * 1000,
		"7d":  7 * 24 * 60 * 60 * 1000,
		"30d": 30 * 24 * 60 * 60 * 1000,
	}
	for w, want := range cases {
		got, err := domains.ParseDomainWindow(w)
		if err != nil {
			t.Errorf("%q: unexpected error: %v", w, err)
		}
		if got != want {
			t.Errorf("%q = %d, want %d", w, got, want)
		}
	}
	// Should reject "1h".
	_, err := domains.ParseDomainWindow("1h")
	if err == nil {
		t.Error("1h: expected error")
	}
}

// TestDomainsAggregateDomains mirrors "aggregateDomains groups jobs by domain and computes success_rate".
func TestDomainsAggregateDomains(t *testing.T) {
	now := time.Now().UnixMilli()
	windowMs := int64(7 * 24 * 60 * 60 * 1000)
	jobs := []domains.RawJob{
		{ID: "a", Domain: "amazon.fr", StartTime: isoOffset(now, -1000), Status: "finished", CrawlMode: "standard"},
		{ID: "b", Domain: "amazon.fr", StartTime: isoOffset(now, -60000), Status: "failed", OOMRestartCount: 1},
		{ID: "c", Domain: "leroymerlin.fr", StartTime: isoOffset(now, -5000), Status: "finished", CrawlMode: "update"},
		{ID: "d", Domain: "leroymerlin.fr", StartTime: isoOffset(now, -8000), Status: "running"},
		// Outside window.
		{ID: "old", Domain: "amazon.fr", StartTime: isoOffset(now, -8*24*60*60*1000), Status: "finished"},
		// Missing domain — should be ignored.
		{ID: "no-domain", StartTime: isoOffset(now, -1000), Status: "finished"},
	}
	result := domains.AggregateDomains(jobs, now, windowMs)
	if len(result) != 2 {
		t.Fatalf("len(result) = %d, want 2", len(result))
	}

	// Find entries by domain name.
	var amz, lm *domains.DomainSummary
	for i := range result {
		switch result[i].Domain {
		case "amazon.fr":
			amz = &result[i]
		case "leroymerlin.fr":
			lm = &result[i]
		}
	}
	if amz == nil {
		t.Fatal("amazon.fr missing")
	}
	if lm == nil {
		t.Fatal("leroymerlin.fr missing")
	}

	// amazon.fr checks.
	if amz.TotalJobs != 2 {
		t.Errorf("amz.total_jobs = %d, want 2", amz.TotalJobs)
	}
	if amz.Success != 1 {
		t.Errorf("amz.success = %d, want 1", amz.Success)
	}
	if amz.Failure != 1 {
		t.Errorf("amz.failure = %d, want 1", amz.Failure)
	}
	if amz.SuccessRate == nil || *amz.SuccessRate != 0.5 {
		t.Errorf("amz.success_rate = %v, want 0.5", amz.SuccessRate)
	}
	if amz.OOMTotal != 1 {
		t.Errorf("amz.oom_total = %d, want 1", amz.OOMTotal)
	}

	// leroymerlin.fr checks.
	if lm.TotalJobs != 2 {
		t.Errorf("lm.total_jobs = %d, want 2", lm.TotalJobs)
	}
	if lm.Success != 1 {
		t.Errorf("lm.success = %d, want 1", lm.Success)
	}
	if lm.Running != 1 {
		t.Errorf("lm.running = %d, want 1", lm.Running)
	}
	if lm.SuccessRate == nil || *lm.SuccessRate != 1.0 {
		t.Errorf("lm.success_rate = %v, want 1.0", lm.SuccessRate)
	}
	if lm.UpdateShare != 0.5 {
		t.Errorf("lm.update_share = %f, want 0.5", lm.UpdateShare)
	}

	// Sorted by last_run_at desc: amazon (1000ms ago) first.
	if result[0].Domain != "amazon.fr" {
		t.Errorf("result[0].domain = %q, want amazon.fr", result[0].Domain)
	}
}

// TestDomainsAggregateDomains_NullSuccessRate mirrors "returns null success_rate when no terminal jobs".
func TestDomainsAggregateDomains_NullSuccessRate(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []domains.RawJob{
		{ID: "x", Domain: "foo.com", StartTime: isoOffset(now, 0), Status: "running"},
	}
	result := domains.AggregateDomains(jobs, now, 7*24*60*60*1000)
	if len(result) != 1 {
		t.Fatalf("len = %d, want 1", len(result))
	}
	if result[0].SuccessRate != nil {
		t.Errorf("success_rate = %v, want nil", *result[0].SuccessRate)
	}
}

// TestDomainsJobsForDomain_FilterAndChain mirrors "filters and builds a chain via previous_crawl_id".
func TestDomainsJobsForDomain_FilterAndChain(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []domains.RawJob{
		{ID: "4", Domain: "a.com", StartTime: isoOffset(now, -1000), Status: "running", PreviousCrawlID: "3"},
		{ID: "3", Domain: "a.com", StartTime: isoOffset(now, -30000), Status: "failed", PreviousCrawlID: "2"},
		{ID: "2", Domain: "a.com", StartTime: isoOffset(now, -60000), Status: "finished", PreviousCrawlID: "1"},
		{ID: "1", Domain: "a.com", StartTime: isoOffset(now, -90000), Status: "finished"},
		{ID: "other", Domain: "b.com", StartTime: isoOffset(now, 0), Status: "finished"},
	}
	detail := domains.JobsForDomain(jobs, "a.com", 7*24*60*60*1000, now)
	if len(detail.Jobs) != 4 {
		t.Fatalf("len(jobs) = %d, want 4", len(detail.Jobs))
	}
	if detail.Jobs[0].ID != "4" {
		t.Errorf("jobs[0].id = %q, want 4", detail.Jobs[0].ID)
	}
	if len(detail.Chain) != 4 {
		t.Fatalf("len(chain) = %d, want 4", len(detail.Chain))
	}
	ids := make([]string, len(detail.Chain))
	for i, c := range detail.Chain {
		ids[i] = c.ID
	}
	want := []string{"4", "3", "2", "1"}
	for i, w := range want {
		if ids[i] != w {
			t.Errorf("chain[%d].id = %q, want %q", i, ids[i], w)
		}
	}
}

// TestDomainsJobsForDomain_BrokenChain mirrors "handles broken chain gracefully".
func TestDomainsJobsForDomain_BrokenChain(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []domains.RawJob{
		{ID: "2", Domain: "a.com", StartTime: isoOffset(now, 0), Status: "running", PreviousCrawlID: "missing"},
		{ID: "1", Domain: "a.com", StartTime: isoOffset(now, -60000), Status: "finished"},
	}
	detail := domains.JobsForDomain(jobs, "a.com", 86400000, now)
	// Chain stops at id 2 because 'missing' is not in the map.
	if len(detail.Chain) != 1 {
		t.Fatalf("len(chain) = %d, want 1", len(detail.Chain))
	}
	if detail.Chain[0].ID != "2" {
		t.Errorf("chain[0].id = %q, want 2", detail.Chain[0].ID)
	}
}

// ---------------------------------------------------------------------------
// HTTP endpoint tests
// ---------------------------------------------------------------------------

func setupDomainsHTTPTest(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)
	now := time.Now()
	// Inject jobs for two domains.
	mr.Set(redisstore.JobPrefix+"a1", fmt.Sprintf(`{"id":"a1","domain":"alpha.com","status":"finished","start_time":%q,"crawl_mode":"standard"}`,
		now.Add(-1*time.Hour).UTC().Format(time.RFC3339)))
	mr.Set(redisstore.JobPrefix+"a2", fmt.Sprintf(`{"id":"a2","domain":"alpha.com","status":"failed","start_time":%q}`,
		now.Add(-2*time.Hour).UTC().Format(time.RFC3339)))
	mr.Set(redisstore.JobPrefix+"b1", fmt.Sprintf(`{"id":"b1","domain":"beta.com","status":"running","start_time":%q}`,
		now.Add(-30*time.Minute).UTC().Format(time.RFC3339)))

	rs, err := redisstore.New("redis://" + mr.Addr())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = rs.Close() })
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	tok := mintToken("admin", "test-secret")
	return srv, tok
}

// TestDomainsHTTP_List checks GET /api/domains returns 200 with domain list.
func TestDomainsHTTP_List(t *testing.T) {
	srv, tok := setupDomainsHTTPTest(t)
	resp, err := authedGet(srv.URL+"/api/domains?window=7d", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body []domains.DomainSummary
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if len(body) != 2 {
		t.Errorf("len(body) = %d, want 2", len(body))
	}
}

// TestDomainsHTTP_DefaultWindow checks that missing window defaults to 7d.
func TestDomainsHTTP_DefaultWindow(t *testing.T) {
	srv, tok := setupDomainsHTTPTest(t)
	resp, _ := authedGet(srv.URL+"/api/domains", tok)
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want 200", resp.StatusCode)
	}
}

// TestDomainsHTTP_BadWindow checks 400 on invalid window.
func TestDomainsHTTP_BadWindow(t *testing.T) {
	srv, tok := setupDomainsHTTPTest(t)
	resp, _ := authedGet(srv.URL+"/api/domains?window=1h", tok)
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", resp.StatusCode)
	}
}

// TestDomainsHTTP_GetDomain checks GET /api/domains/{domain} returns jobs + chain.
func TestDomainsHTTP_GetDomain(t *testing.T) {
	srv, tok := setupDomainsHTTPTest(t)
	resp, err := authedGet(srv.URL+"/api/domains/alpha.com?window=7d", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body domains.DomainDetail
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if len(body.Jobs) != 2 {
		t.Errorf("len(jobs) = %d, want 2", len(body.Jobs))
	}
}

// TestDomainsHTTP_NoAuth checks that unauthenticated requests are rejected.
func TestDomainsHTTP_NoAuth(t *testing.T) {
	srv, _ := setupDomainsHTTPTest(t)
	resp, _ := http.Get(srv.URL + "/api/domains")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", resp.StatusCode)
	}
}
