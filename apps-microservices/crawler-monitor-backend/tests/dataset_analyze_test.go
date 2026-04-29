package tests

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// TestDatasetAnalyze_NoDuplicates vérifie qu'un dataset sans doublons retourne
// duplicates=0 et by_url vide.
func TestDatasetAnalyze_NoDuplicates(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "analyze-no-dup-job"
	base := fs.Base()

	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)
	for i := 0; i < 4; i++ {
		content := fmt.Sprintf(`{"url":"https://example.com/page%d"}`, i)
		os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), []byte(content), 0o644)
	}

	resp, err := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/analyze", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(4) {
		t.Errorf("total=%v want 4", body["total"])
	}
	if body["unique"] != float64(4) {
		t.Errorf("unique=%v want 4", body["unique"])
	}
	if body["duplicates"] != float64(0) {
		t.Errorf("duplicates=%v want 0", body["duplicates"])
	}
	byURL, _ := body["by_url"].([]any)
	if len(byURL) != 0 {
		t.Errorf("by_url len=%d want 0", len(byURL))
	}
}

// TestDatasetAnalyze_WithDuplicates vérifie que les groupes de doublons sont correctement identifiés.
func TestDatasetAnalyze_WithDuplicates(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "analyze-dup-job"
	base := fs.Base()

	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)

	// URL "https://example.com/dup" apparaît dans 3 fichiers → 2 doublons
	for i := 0; i < 3; i++ {
		content := `{"url":"https://example.com/dup"}`
		os.WriteFile(filepath.Join(dir, fmt.Sprintf("dup_%d.json", i)), []byte(content), 0o644)
	}
	// 1 URL unique
	os.WriteFile(filepath.Join(dir, "unique.json"), []byte(`{"url":"https://example.com/unique"}`), 0o644)

	resp, _ := authedGet(srv.URL+"/api/jobs/"+jobID+"/dataset/analyze", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	if body["total"] != float64(4) {
		t.Errorf("total=%v want 4", body["total"])
	}
	if body["unique"] != float64(2) {
		t.Errorf("unique=%v want 2", body["unique"])
	}
	if body["duplicates"] != float64(2) {
		t.Errorf("duplicates=%v want 2", body["duplicates"])
	}
	byURL, _ := body["by_url"].([]any)
	if len(byURL) != 1 {
		t.Fatalf("by_url len=%d want 1", len(byURL))
	}
	group, _ := byURL[0].(map[string]any)
	if group["url"] != "https://example.com/dup" {
		t.Errorf("group url=%v want https://example.com/dup", group["url"])
	}
	if group["count"] != float64(3) {
		t.Errorf("group count=%v want 3", group["count"])
	}
}

// TestDatasetAnalyze_Empty vérifie qu'un job sans dataset retourne des zéros.
func TestDatasetAnalyze_Empty(t *testing.T) {
	srv, _, tok := setupDatasetServer(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/analyze-empty-job/dataset/analyze", tok)
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["total"] != float64(0) || body["unique"] != float64(0) || body["duplicates"] != float64(0) {
		t.Errorf("expected zeros, got %v", body)
	}
}

// TestDatasetDedup_KeepsNewest vérifie que deduplicate garde le fichier le plus récent.
func TestDatasetDedup_KeepsNewest(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "dedup-keep-newest-job"
	base := fs.Base()

	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)

	// 3 fichiers avec la même URL mais mtime différents
	// On crée avec un délai simulé via os.Chtimes
	url := "https://example.com/page"
	for i := 0; i < 3; i++ {
		fname := fmt.Sprintf("dup_%d.json", i)
		content := fmt.Sprintf(`{"url":%q}`, url)
		fpath := filepath.Join(dir, fname)
		os.WriteFile(fpath, []byte(content), 0o644)
		// Mtime simulé : i*seconde pour distinguer les fichiers
		mtime := time.Now().Add(time.Duration(i) * time.Second)
		os.Chtimes(fpath, mtime, mtime)
	}

	// 1 fichier unique à conserver
	os.WriteFile(filepath.Join(dir, "unique.json"), []byte(`{"url":"https://example.com/unique"}`), 0o644)

	resp, err := postJSON(srv.URL+"/api/jobs/"+jobID+"/dataset/deduplicate", tok, nil)
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

	// Vérifie qu'il reste 2 fichiers (1 dup le plus récent + 1 unique)
	remaining, _ := os.ReadDir(dir)
	if len(remaining) != 2 {
		t.Errorf("remaining=%d want 2", len(remaining))
	}
}

// TestDatasetDedup_NoDuplicates vérifie que sur un dataset sans doublons, rien n'est supprimé.
func TestDatasetDedup_NoDuplicates(t *testing.T) {
	srv, fs, tok := setupDatasetServer(t)
	jobID := "dedup-no-dup-job"
	base := fs.Base()

	dir := filepath.Join(base, jobID, "storage", "datasets", "example.com")
	os.MkdirAll(dir, 0o755)
	for i := 0; i < 3; i++ {
		content := fmt.Sprintf(`{"url":"https://example.com/page%d"}`, i)
		os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), []byte(content), 0o644)
	}

	resp, _ := postJSON(srv.URL+"/api/jobs/"+jobID+"/dataset/deduplicate", tok, nil)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["deleted"] != float64(0) {
		t.Errorf("deleted=%v want 0", body["deleted"])
	}
}
