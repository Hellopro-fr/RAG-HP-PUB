package tests

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// writeCrawleeFile writes a Crawlee v3 on-disk JSON file for a request-queue entry.
// isHandled sets orderNo to null (handled marker in Crawlee v3).
func writeCrawleeFile(t *testing.T, dir, name, url, method string, retryCount int, isHandled bool) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	var orderNo any
	if isHandled {
		orderNo = nil
	} else {
		orderNo = time.Now().UnixMilli()
	}
	entry := map[string]any{
		"id":            fmt.Sprintf("req_%s", name),
		"url":           url,
		"method":        method,
		"orderNo":       orderNo,
		"retryCount":    retryCount,
		"uniqueKey":     url,
		"errorMessages": []string{},
	}
	b, _ := json.Marshal(entry)
	if err := os.WriteFile(filepath.Join(dir, name), b, 0o644); err != nil {
		t.Fatal(err)
	}
}

func setupQueuesTest(t *testing.T) (string, string, string) {
	t.Helper()
	srv, fs, tok := setupDatasetServer(t)
	return srv.URL, fs.Base(), tok
}

func TestQueuesList_StatusPendingExcludesHandled(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-status-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")

	// 3 pending + 2 handled
	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)
	writeCrawleeFile(t, dir, "1.json", "https://example.com/p2", "GET", 0, false)
	writeCrawleeFile(t, dir, "2.json", "https://example.com/p3", "GET", 0, false)
	writeCrawleeFile(t, dir, "3.json", "https://example.com/h1", "GET", 0, true)
	writeCrawleeFile(t, dir, "4.json", "https://example.com/h2", "GET", 0, true)

	resp, _ := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues?status=pending&limit=100", tok)
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(3) {
		t.Errorf("total=%v want 3", body["total"])
	}
	items, _ := body["items"].([]any)
	for _, it := range items {
		m := it.(map[string]any)
		url := m["url"].(string)
		if !strings.Contains(url, "/p") {
			t.Errorf("pending filter returned handled url=%q", url)
		}
	}
}

func TestQueuesList_StatusHandledExcludesPending(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-handled-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")

	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)
	writeCrawleeFile(t, dir, "1.json", "https://example.com/h1", "GET", 0, true)
	writeCrawleeFile(t, dir, "2.json", "https://example.com/h2", "GET", 0, true)

	resp, _ := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues?status=handled&limit=100", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(2) {
		t.Errorf("total=%v want 2", body["total"])
	}
	items, _ := body["items"].([]any)
	for _, it := range items {
		m := it.(map[string]any)
		url := m["url"].(string)
		if !strings.Contains(url, "/h") {
			t.Errorf("handled filter returned pending url=%q", url)
		}
	}
}

func TestQueuesList_StatusAll(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-all-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")

	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)
	writeCrawleeFile(t, dir, "1.json", "https://example.com/p2", "GET", 0, false)
	writeCrawleeFile(t, dir, "2.json", "https://example.com/h1", "GET", 0, true)

	resp, _ := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues?limit=100", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(3) {
		t.Errorf("total=%v want 3", body["total"])
	}
}

func TestQueuesList_CountsAlwaysUnfiltered(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-counts-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")

	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)
	writeCrawleeFile(t, dir, "1.json", "https://example.com/p2", "GET", 0, false)
	writeCrawleeFile(t, dir, "2.json", "https://example.com/p3", "GET", 0, false)
	writeCrawleeFile(t, dir, "3.json", "https://example.com/h1", "GET", 0, true)
	writeCrawleeFile(t, dir, "4.json", "https://example.com/h2", "GET", 0, true)

	expected := map[string]float64{"total": 5, "pending": 3, "handled": 2}
	for _, status := range []string{"all", "pending", "handled"} {
		resp, _ := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues?status="+status, tok)
		var body map[string]any
		decodeJSON(t, resp.Body, &body)
		counts, _ := body["counts"].(map[string]any)
		for k, want := range expected {
			if counts[k] != want {
				t.Errorf("status=%s counts.%s=%v want %v", status, k, counts[k], want)
			}
		}
	}
}

func TestQueuesStatus_ReadFile(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-read-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")
	writeCrawleeFile(t, dir, "0.json", "https://example.com/page1", "GET", 0, false)

	resp, _ := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues/example.com/0.json", tok)
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["url"] != "https://example.com/page1" {
		t.Errorf("url=%v", body["url"])
	}
}

func TestQueuesStatus_ReadFileNotFound(t *testing.T) {
	srvURL, _, tok := setupQueuesTest(t)
	resp, _ := authedGet(srvURL+"/api/jobs/nonexistent-job/request-queues/example.com/missing.json", tok)
	if resp.StatusCode != 404 {
		t.Errorf("expected 404, got %d", resp.StatusCode)
	}
}

func TestQueuesStatus_PathTraversalRejected(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-traversal-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")
	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)

	// Attempt path traversal via domain component.
	resp, _ := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues/..%2F..%2Fetc/passwd", tok)
	if resp.StatusCode == 200 {
		t.Errorf("expected 4xx for path traversal, got 200")
	}
}

func TestQueuesStatus_WriteFile(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "rq-write-job"
	dir := filepath.Join(base, jobID, "storage", "request_queues", "example.com")
	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)

	updated := map[string]any{"url": "https://example.com/p1-updated", "method": "GET", "orderNo": nil}
	payload, _ := json.Marshal(updated)

	req, _ := http.NewRequest("POST",
		srvURL+"/api/jobs/"+jobID+"/request-queues/example.com/0.json",
		bytes.NewReader(payload))
	req.Header.Set("Authorization", "Bearer "+tok)
	req.Header.Set("Content-Type", "application/json")
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
	if body["status"] != "ok" {
		t.Errorf("status=%v want ok", body["status"])
	}

	// Verify file was written.
	raw, _ := os.ReadFile(filepath.Join(dir, "0.json"))
	if !strings.Contains(string(raw), "p1-updated") {
		t.Errorf("file not updated, content=%s", raw)
	}
}

func TestQueuesList_EmptyJobReturnsZeros(t *testing.T) {
	srvURL, _, tok := setupQueuesTest(t)
	resp, _ := authedGet(srvURL+"/api/jobs/no-such-job/request-queues", tok)
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(0) {
		t.Errorf("total=%v want 0", body["total"])
	}
	counts, _ := body["counts"].(map[string]any)
	if counts["total"] != float64(0) {
		t.Errorf("counts.total=%v want 0", counts["total"])
	}
}
