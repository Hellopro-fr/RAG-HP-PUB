package tests

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
)

func TestAudit_AppendThenRead(t *testing.T) {
	dir := t.TempDir()
	l := auditstore.New(dir)
	for i := 0; i < 3; i++ {
		_ = l.Append(context.Background(), map[string]any{"action": "x", "user": "admin", "status": "ok"})
	}
	page, err := l.Read(context.Background(), auditstore.Filter{
		From: time.Now().Add(-1 * time.Hour),
		To:   time.Now().Add(1 * time.Hour),
	})
	if err != nil {
		t.Fatal(err)
	}
	if page.Total != 3 {
		t.Errorf("total=%d, want 3", page.Total)
	}
}

func TestAudit_FormatMatchesNode(t *testing.T) {
	dir := t.TempDir()
	day := time.Now().UTC().Format("2006-01-02")
	nodeContent := `{"ts":"` + time.Now().UTC().Format(time.RFC3339Nano) + `","user":"admin","action":"login_success","target":null,"status":"ok","ip":"127.0.0.1","metadata":null}` + "\n"
	_ = os.WriteFile(filepath.Join(dir, "audit-"+day+".log"), []byte(nodeContent), 0o644)
	l := auditstore.New(dir)
	page, err := l.Read(context.Background(), auditstore.Filter{
		From: time.Now().Add(-24 * time.Hour),
		To:   time.Now().Add(24 * time.Hour),
	})
	if err != nil {
		t.Fatal(err)
	}
	if page.Total != 1 {
		t.Fatalf("total=%d, want 1", page.Total)
	}
	got := page.Items[0]
	if got["action"] != "login_success" || got["user"] != "admin" {
		t.Errorf("entry mismatch: %+v", got)
	}
	_ = l.Append(context.Background(), map[string]any{"action": "x", "user": "admin", "status": "ok"})
	raw, _ := os.ReadFile(filepath.Join(dir, "audit-"+day+".log"))
	lines := strings.Count(string(raw), "\n")
	if lines < 2 {
		t.Errorf("expected >=2 lines, got %d", lines)
	}
}

func TestAudit_RotateOld(t *testing.T) {
	dir := t.TempDir()
	old := time.Now().Add(-100 * 24 * time.Hour).UTC().Format("2006-01-02")
	recent := time.Now().UTC().Format("2006-01-02")
	_ = os.WriteFile(filepath.Join(dir, "audit-"+old+".log"), []byte("{}\n"), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "audit-"+recent+".log"), []byte("{}\n"), 0o644)
	l := auditstore.New(dir)
	deleted, err := l.RotateOld(context.Background(), 90)
	if err != nil {
		t.Fatal(err)
	}
	if deleted != 1 {
		t.Errorf("deleted=%d, want 1", deleted)
	}
	if _, err := os.Stat(filepath.Join(dir, "audit-"+recent+".log")); err != nil {
		t.Errorf("recent file should remain: %v", err)
	}
}

func TestAudit_WindowTooWide(t *testing.T) {
	l := auditstore.New(t.TempDir())
	_, err := l.Read(context.Background(), auditstore.Filter{
		From: time.Now().Add(-60 * 24 * time.Hour),
		To:   time.Now(),
	})
	if err == nil {
		t.Error("expected window-too-wide error")
	}
}
