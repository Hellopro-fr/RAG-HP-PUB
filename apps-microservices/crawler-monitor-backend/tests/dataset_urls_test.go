package tests

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

func TestDatasetURLs_Pagination(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "urls-test-job"
	base := fs.Base()

	// 25 success URLs
	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 25; i++ {
		content := fmt.Sprintf(`{"url":"https://example.com/success/%d"}`, i)
		os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), []byte(content), 0o644)
	}

	// Page 2, limit 10 → items 10-19 (0-indexed), total 25, totalPages 3
	resp, err := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/urls?category=success&page=2&limit=10", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(25) {
		t.Errorf("total=%v want 25", body["total"])
	}
	if body["page"] != float64(2) {
		t.Errorf("page=%v want 2", body["page"])
	}
	if body["totalPages"] != float64(3) {
		t.Errorf("totalPages=%v want 3", body["totalPages"])
	}
	items, _ := body["items"].([]any)
	if len(items) != 10 {
		t.Errorf("len(items)=%d want 10", len(items))
	}
}

func TestDatasetURLs_SearchCaseInsensitive(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "urls-search-job"
	base := fs.Base()
	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)
	for i := 0; i < 25; i++ {
		content := fmt.Sprintf(`{"url":"https://example.com/success/%d"}`, i)
		os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), []byte(content), 0o644)
	}

	// search=SUCCESS/1 should match success/1, success/10..19 → 11 items
	resp, _ := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/urls?category=success&search=SUCCESS/1", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(11) {
		t.Errorf("total=%v want 11", body["total"])
	}
}

func TestDatasetURLs_ErrorCategory(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "urls-error-job"
	base := fs.Base()
	dir := filepath.Join(base, jobID, "storage", "datasets", "error-example.com")
	os.MkdirAll(dir, 0o755)

	entries := []struct{ name, content string }{
		{"0.json", `{"url":"https://example.com/err/1","errorMessages":["HTTP 500 Server Error"]}`},
		{"1.json", `{"url":"https://example.com/err/2","statusCode":404,"statusText":"Not Found"}`},
		{"2.json", `{"url":"https://example.com/err/3"}`},
	}
	for _, e := range entries {
		os.WriteFile(filepath.Join(dir, e.name), []byte(e.content), 0o644)
	}

	resp, _ := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/urls?category=error&limit=50", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(3) {
		t.Errorf("total=%v want 3", body["total"])
	}
	items, _ := body["items"].([]any)
	byURL := map[string]string{}
	for _, it := range items {
		m := it.(map[string]any)
		byURL[m["url"].(string)] = m["error"].(string)
	}
	if byURL["https://example.com/err/1"] != "HTTP 500 Server Error" {
		t.Errorf("err/1 error=%q", byURL["https://example.com/err/1"])
	}
	if byURL["https://example.com/err/2"] != "HTTP 404 Not Found" {
		t.Errorf("err/2 error=%q", byURL["https://example.com/err/2"])
	}
	if byURL["https://example.com/err/3"] != "Unknown error" {
		t.Errorf("err/3 error=%q", byURL["https://example.com/err/3"])
	}
}

func TestDatasetURLs_InvalidCategory(t *testing.T) {
	srv, _, tok := setupDatasetServer(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/some-job/dataset/urls?category=foo", tok)
	if resp.StatusCode != 400 {
		t.Errorf("expected 400, got %d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["error"] == nil {
		t.Error("expected error field")
	}
}

func TestDatasetURLs_MalformedFilesSkipped(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "urls-malformed-job"
	base := fs.Base()
	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)
	os.WriteFile(filepath.Join(dir, "0.json"), []byte(`{"url":"https://example.com/ok"}`), 0o644)
	os.WriteFile(filepath.Join(dir, "broken.json"), []byte(`{not valid json`), 0o644)

	resp, _ := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/urls?category=success", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(1) {
		t.Errorf("total=%v want 1", body["total"])
	}
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("len(items)=%d want 1", len(items))
	}
	m := items[0].(map[string]any)
	if m["url"] != "https://example.com/ok" {
		t.Errorf("url=%v", m["url"])
	}
}

func TestDatasetURLs_LimitCapped(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "urls-limit-job"
	base := fs.Base()
	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)
	for i := 0; i < 25; i++ {
		content := fmt.Sprintf(`{"url":"https://example.com/success/%d"}`, i)
		os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), []byte(content), 0o644)
	}

	// limit=9999 should be capped at 200; page=0 should default to 1
	resp, _ := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/urls?category=success&page=0&limit=9999", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["page"] != float64(1) {
		t.Errorf("page=%v want 1", body["page"])
	}
	items, _ := body["items"].([]any)
	// All 25 items returned since 25 < 200
	if len(items) != 25 {
		t.Errorf("len(items)=%d want 25", len(items))
	}
}

func TestDatasetURLs_NoAuth(t *testing.T) {
	srv, _, _ := setupDatasetServer(t)
	resp, _ := http.Get(srv.URL + "/api/jobs/some-job/dataset/counts")
	if resp.StatusCode != 401 {
		t.Errorf("expected 401, got %d", resp.StatusCode)
	}
}
