package tests

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

// TestQueuesAnalyze_Empty vérifie que l'analyse d'un job sans fichiers retourne total=0.
func TestQueuesAnalyze_Empty(t *testing.T) {
	srvURL, _, tok := setupQueuesTest(t)
	resp, err := authedGet(srvURL+"/api/jobs/nonexistent-analyze-job/request-queues/analyze", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("expected 200, got %d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(0) {
		t.Errorf("total=%v want 0", body["total"])
	}
	if body["blocked"] != float64(0) {
		t.Errorf("blocked=%v want 0", body["blocked"])
	}
	if body["valid"] != float64(0) {
		t.Errorf("valid=%v want 0", body["valid"])
	}
}

// TestQueuesAnalyze_ValidAndBlocked vérifie le comptage correct des URLs valides et bloquées.
func TestQueuesAnalyze_ValidAndBlocked(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "analyze-mixed-job"
	domain := "example.com"

	// 2 URLs valides
	writeQueueFile(t, base, jobID, domain, "0.json", "https://example.com/produit/ref-123")
	writeQueueFile(t, base, jobID, domain, "1.json", "https://example.com/categorie/informatique")
	// 1 URL bloquée (PDF — correspond au pattern extension)
	writeQueueFile(t, base, jobID, domain, "2.json", "https://example.com/fiche.pdf")
	// 1 URL bloquée (panier — pattern auth/shopping)
	writeQueueFile(t, base, jobID, domain, "3.json", "https://example.com/panier/mon-panier")

	resp, err := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues/analyze", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}

	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	if body["total"] != float64(4) {
		t.Errorf("total=%v want 4", body["total"])
	}
	if body["valid"] != float64(2) {
		t.Errorf("valid=%v want 2", body["valid"])
	}
	if body["blocked"] != float64(2) {
		t.Errorf("blocked=%v want 2", body["blocked"])
	}
}

// TestQueuesAnalyze_HandledPendingCounts vérifie le comptage pending/handled.
func TestQueuesAnalyze_HandledPendingCounts(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "analyze-handled-job"
	domain := "example.com"

	dir := filepath.Join(base, jobID, "storage", "request_queues", domain)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}

	// 2 pending + 3 handled
	writeCrawleeFile(t, dir, "0.json", "https://example.com/p1", "GET", 0, false)
	writeCrawleeFile(t, dir, "1.json", "https://example.com/p2", "GET", 0, false)
	writeCrawleeFile(t, dir, "2.json", "https://example.com/h1", "GET", 0, true)
	writeCrawleeFile(t, dir, "3.json", "https://example.com/h2", "GET", 0, true)
	writeCrawleeFile(t, dir, "4.json", "https://example.com/h3", "GET", 0, true)

	resp, err := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues/analyze", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}

	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	if body["pending"] != float64(2) {
		t.Errorf("pending=%v want 2", body["pending"])
	}
	if body["handled"] != float64(3) {
		t.Errorf("handled=%v want 3", body["handled"])
	}
}

// TestQueuesAnalyze_ExamplesPopulated vérifie que les exemples sont remplis.
func TestQueuesAnalyze_ExamplesPopulated(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "analyze-examples-job"
	domain := "example.com"

	// 1 URL bloquée + 1 URL valide
	writeQueueFile(t, base, jobID, domain, "0.json", "https://example.com/page-produit")
	writeQueueFile(t, base, jobID, domain, "1.json", "https://example.com/cart")

	resp, err := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues/analyze", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}

	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	examples, ok := body["examples"].(map[string]any)
	if !ok {
		t.Fatalf("examples field missing or wrong type, got %T", body["examples"])
	}

	validExamples, _ := examples["valid"].([]any)
	if len(validExamples) == 0 {
		t.Errorf("expected at least 1 valid example, got %v", examples["valid"])
	}
	blockedExamples, _ := examples["blocked"].([]any)
	if len(blockedExamples) == 0 {
		t.Errorf("expected at least 1 blocked example, got %v", examples["blocked"])
	}
	// Chaque blocked example doit avoir url et pattern
	for _, ex := range blockedExamples {
		m, ok := ex.(map[string]any)
		if !ok {
			t.Errorf("blocked example should be object, got %T", ex)
			continue
		}
		if m["url"] == nil || m["pattern"] == nil {
			t.Errorf("blocked example missing url or pattern: %v", m)
		}
	}
}

// TestQueuesAnalyze_RecommendationAllBlocked vérifie la recommandation quand >90% sont bloquées.
func TestQueuesAnalyze_RecommendationAllBlocked(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "analyze-all-blocked"
	domain := "example.com"

	// 10 URLs bloquées (cart pattern) + 0 valides
	for i := 0; i < 10; i++ {
		writeQueueFile(t, base, jobID, domain,
			string(rune('0'+i))+".json",
			"https://example.com/cart/item-"+string(rune('a'+i)))
	}

	resp, err := authedGet(srvURL+"/api/jobs/"+jobID+"/request-queues/analyze", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}

	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	rec, _ := body["recommendation"].(string)
	if rec == "" {
		t.Errorf("recommendation should be non-empty")
	}
}

// TestQueuesAnalyze_NoAuth vérifie que les requêtes non authentifiées sont rejetées.
func TestQueuesAnalyze_NoAuth(t *testing.T) {
	srvURL, _, _ := setupQueuesTest(t)
	resp, _ := http.Get(srvURL + "/api/jobs/some-job/request-queues/analyze")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", resp.StatusCode)
	}
}
