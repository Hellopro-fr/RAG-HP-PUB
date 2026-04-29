package tests

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// setupDatasetServer creates a test server with a FileStore backed by a temp directory.
func setupDatasetServer(t *testing.T) (*httptest.Server, *filestore.Storage, string) {
	t.Helper()
	base := t.TempDir()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	t.Cleanup(func() { rs.Close() })
	fs := filestore.New(base)
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, FileStore: fs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, fs, mintToken("admin", "test-secret")
}

// writeDatasetFile creates a JSON file in base/<jobID>/storage/datasets/<subdir>/<name>.json.
func writeDatasetFile(t *testing.T, base, jobID, subdir, name string, content any) {
	t.Helper()
	dir := filepath.Join(base, jobID, "storage", "datasets", subdir)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	b, _ := json.Marshal(content)
	if err := os.WriteFile(filepath.Join(dir, name), b, 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestDatasetCounts_Full(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "counts-test-job"
	base := fs.Base()

	// success: 2 files
	writeDatasetFile(t, base, jobID, "example.com", "0.json", map[string]any{"url": "https://example.com/a"})
	writeDatasetFile(t, base, jobID, "example.com", "1.json", map[string]any{"url": "https://example.com/b"})
	// error: 1 file
	writeDatasetFile(t, base, jobID, "error-example.com", "0.json", map[string]any{
		"url": "https://example.com/x", "errorMessages": []string{"HTTP 500"},
	})
	// nfr: 3 files
	for i := 0; i < 3; i++ {
		writeDatasetFile(t, base, jobID, "nfr-example.com", fmt.Sprintf("%d.json", i),
			map[string]any{"url": fmt.Sprintf("https://example.com/fr/%d", i+1)})
	}

	resp, err := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/counts", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["success"] != float64(2) {
		t.Errorf("success=%v want 2", body["success"])
	}
	if body["error"] != float64(1) {
		t.Errorf("error=%v want 1", body["error"])
	}
	if body["nfr"] != float64(3) {
		t.Errorf("nfr=%v want 3", body["nfr"])
	}
}

func TestDatasetCounts_SuccessOnly(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "counts-solo-job"
	base := fs.Base()
	writeDatasetFile(t, base, jobID, "example.com", "0.json", map[string]any{"url": "https://example.com/a"})

	resp, _ := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/counts", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["success"] != float64(1) || body["error"] != float64(0) || body["nfr"] != float64(0) {
		t.Errorf("body=%v", body)
	}
}

func TestDatasetCounts_Empty(t *testing.T) {
	srv, _, tok := setupDatasetServer(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/counts-empty-job/dataset/counts", tok)
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["success"] != float64(0) || body["error"] != float64(0) || body["nfr"] != float64(0) {
		t.Errorf("expected all zeros, got %v", body)
	}
}
