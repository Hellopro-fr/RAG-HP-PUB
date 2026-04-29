package tests

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func TestAuditEndpoint_List(t *testing.T) {
	dir := t.TempDir()
	store := auditstore.New(dir)
	for i := 0; i < 3; i++ {
		_ = store.Append(context.Background(), map[string]any{
			"action": "x", "user": "admin", "status": "ok",
		})
	}
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())

	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config:     cfg,
		RedisStore: rs,
		AuditStore: httpapi.WrapAuditStore(store),
	}))
	defer srv.Close()

	resp, err := authedGet(srv.URL+"/api/audit", mintToken("admin", "test-secret"))
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&body)
	if int(body["total"].(float64)) != 3 {
		t.Errorf("total=%v", body["total"])
	}
}

func TestAuditEndpoint_WindowTooWide(t *testing.T) {
	dir := t.TempDir()
	store := auditstore.New(dir)
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())

	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config:     cfg,
		RedisStore: rs,
		AuditStore: httpapi.WrapAuditStore(store),
	}))
	defer srv.Close()

	from := time.Now().Add(-60 * 24 * time.Hour).Format(time.RFC3339)
	to := time.Now().Format(time.RFC3339)
	resp, _ := authedGet(srv.URL+"/api/audit?from="+from+"&to="+to, mintToken("admin", "test-secret"))
	if resp.StatusCode != 400 {
		t.Errorf("status=%d, want 400 (window too wide)", resp.StatusCode)
	}
}
