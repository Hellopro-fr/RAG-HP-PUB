package tests

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

// writeQueueFile crée un fichier Crawlee JSON dans base/<jobID>/storage/request_queues/<domain>/<name>.
func writeQueueFile(t *testing.T, base, jobID, domain, name, rawURL string) {
	t.Helper()
	dir := filepath.Join(base, jobID, "storage", "request_queues", domain)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	content := map[string]any{
		"id":            fmt.Sprintf("req_%s", name),
		"url":           rawURL,
		"method":        "GET",
		"orderNo":       1,
		"retryCount":    0,
		"uniqueKey":     rawURL,
		"errorMessages": []string{},
	}
	b, _ := json.Marshal(content)
	if err := os.WriteFile(filepath.Join(dir, name), b, 0o644); err != nil {
		t.Fatal(err)
	}
}

// postJSON envoie une requête POST JSON authentifiée.
func postJSON(url, token string, payload any) (*http.Response, error) {
	b, _ := json.Marshal(payload)
	req, err := http.NewRequest("POST", url, bytes.NewReader(b))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	return http.DefaultClient.Do(req)
}

// TestQueuesMutations_CleanPatternsDeletesMatching vérifie que clean-patterns supprime
// uniquement les fichiers dont l'URL correspond aux patterns fournis.
func TestQueuesMutations_CleanPatternsDeletesMatching(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "clean-patterns-job"
	domain := "example.com"

	// 2 fichiers PDF → doivent être supprimés
	writeQueueFile(t, base, jobID, domain, "0.json", "https://example.com/doc.pdf")
	writeQueueFile(t, base, jobID, domain, "1.json", "https://example.com/manual.pdf")
	// 2 fichiers HTML normaux → doivent rester
	writeQueueFile(t, base, jobID, domain, "2.json", "https://example.com/page1")
	writeQueueFile(t, base, jobID, domain, "3.json", "https://example.com/page2")

	payload := map[string]any{"patterns": []string{"**/*.pdf"}}
	resp, err := postJSON(srvURL+"/api/jobs/"+jobID+"/request-queues/clean-patterns", tok, payload)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != float64(2) {
		t.Errorf("deleted=%v want 2", body["deleted"])
	}

	// Vérifie que les fichiers HTML subsistent
	dir := filepath.Join(base, jobID, "storage", "request_queues", domain)
	remaining, _ := os.ReadDir(dir)
	if len(remaining) != 2 {
		t.Errorf("remaining=%d want 2", len(remaining))
	}
}

// TestQueuesMutations_CleanPatternsEmptyPatterns vérifie qu'avec une liste vide,
// aucun fichier n'est supprimé.
func TestQueuesMutations_CleanPatternsEmptyPatterns(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "clean-empty-patterns-job"
	domain := "example.com"

	writeQueueFile(t, base, jobID, domain, "0.json", "https://example.com/page")
	writeQueueFile(t, base, jobID, domain, "1.json", "https://example.com/other")

	payload := map[string]any{"patterns": []string{}}
	resp, _ := postJSON(srvURL+"/api/jobs/"+jobID+"/request-queues/clean-patterns", tok, payload)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != float64(0) {
		t.Errorf("deleted=%v want 0", body["deleted"])
	}
}

// TestQueuesMutations_RepairDeletesDomainMismatch vérifie que repair supprime
// les fichiers dont le hostname de l'URL ne correspond pas au domaine du dossier.
func TestQueuesMutations_RepairDeletesDomainMismatch(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "repair-job"
	domain := "example.com"

	// URL correcte : hostname == domain ou sous-domaine
	writeQueueFile(t, base, jobID, domain, "0.json", "https://example.com/page")
	writeQueueFile(t, base, jobID, domain, "1.json", "https://sub.example.com/page")
	// URL incorrecte : hostname != domain
	writeQueueFile(t, base, jobID, domain, "2.json", "https://other.com/page")
	writeQueueFile(t, base, jobID, domain, "3.json", "https://evil.org/inject")

	resp, err := postJSON(srvURL+"/api/jobs/"+jobID+"/request-queues/repair", tok, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != float64(2) {
		t.Errorf("deleted=%v want 2", body["deleted"])
	}

	// Vérifie que les 2 fichiers valides restent
	dir := filepath.Join(base, jobID, "storage", "request_queues", domain)
	remaining, _ := os.ReadDir(dir)
	if len(remaining) != 2 {
		t.Errorf("remaining=%d want 2", len(remaining))
	}
}

// TestQueuesMutations_DropDeletesAll vérifie que drop supprime tous les fichiers
// du répertoire request_queues du job.
func TestQueuesMutations_DropDeletesAll(t *testing.T) {
	srvURL, base, tok := setupQueuesTest(t)
	jobID := "drop-all-job"
	domain := "example.com"

	for i := 0; i < 5; i++ {
		writeQueueFile(t, base, jobID, domain, fmt.Sprintf("%d.json", i),
			fmt.Sprintf("https://example.com/page%d", i))
	}

	resp, err := postJSON(srvURL+"/api/jobs/"+jobID+"/request-queues/drop", tok, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != float64(5) {
		t.Errorf("deleted=%v want 5", body["deleted"])
	}

	// Répertoire doit exister mais être vide
	dir := filepath.Join(base, jobID, "storage", "request_queues", domain)
	remaining, _ := os.ReadDir(dir)
	if len(remaining) != 0 {
		t.Errorf("remaining=%d want 0", len(remaining))
	}
}

// TestQueuesMutations_DropEmptyQueue vérifie que drop sur un job inexistant
// retourne deleted=0 sans erreur.
func TestQueuesMutations_DropEmptyQueue(t *testing.T) {
	srvURL, _, tok := setupQueuesTest(t)
	resp, err := postJSON(srvURL+"/api/jobs/nonexistent-job/request-queues/drop", tok, nil)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != float64(0) {
		t.Errorf("deleted=%v want 0", body["deleted"])
	}
}
