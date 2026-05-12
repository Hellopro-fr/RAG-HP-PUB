package routing

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"mcp-zoho-service/internal/db"
)

// stubRunner satisfies QueryRunner with controllable in-memory data so the
// resolver can be tested without a live MySQL.
type stubRunner struct {
	adminRow    *db.ServerRow
	adminErr    error
	importRow   *db.ServerRow
	importErr   error
	grants      map[string]map[string]bool // serverID → email(lowercased) → granted
	adminCalls  int
	grantCalls  int
	importCalls int
}

func (s *stubRunner) FindAdminZohoServer(_ context.Context, _ string) (*db.ServerRow, error) {
	s.adminCalls++
	if s.adminErr != nil {
		return nil, s.adminErr
	}
	if s.adminRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.adminRow, nil
}

func (s *stubRunner) IsAdminGranted(_ context.Context, serverID, email string) (bool, error) {
	s.grantCalls++
	g, ok := s.grants[serverID]
	if !ok {
		return false, nil
	}
	return g[lower(email)], nil
}

func (s *stubRunner) FindUserZohoImport(_ context.Context, _, _ string) (*db.ServerRow, error) {
	s.importCalls++
	if s.importErr != nil {
		return nil, s.importErr
	}
	if s.importRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.importRow, nil
}

// fakeDecryptor returns its input unchanged so tests don't need a real key.
type fakeDecryptor struct{}

func (fakeDecryptor) Decrypt(b []byte) ([]byte, error) { return b, nil }

func TestResolver_AdminGranted(t *testing.T) {
	sr := &stubRunner{
		adminRow: &db.ServerRow{ID: "admin-1", URL: "http://admin-zoho/mcp", AuthHeaders: []byte(`{"Authorization":"Bearer admin"}`)},
		grants:   map[string]map[string]bool{"admin-1": {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, "http://self/mcp")

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://admin-zoho/mcp" {
		t.Fatalf("upstream = %q, want admin", got.UpstreamURL)
	}
	if got.Headers["Authorization"] != "Bearer admin" {
		t.Fatalf("headers = %+v, want admin bearer", got.Headers)
	}
}

func TestResolver_UserImport(t *testing.T) {
	sr := &stubRunner{
		adminRow:  &db.ServerRow{ID: "admin-1", URL: "http://admin-zoho/mcp"},
		grants:    map[string]map[string]bool{},
		importRow: &db.ServerRow{ID: "user-1", URL: "http://alice-zoho/mcp", CreatedBy: "alice@hp.fr", AuthHeaders: []byte(`{"Authorization":"Bearer alice"}`)},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, "http://self/mcp")

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://alice-zoho/mcp" {
		t.Fatalf("upstream = %q, want alice", got.UpstreamURL)
	}
}

func TestResolver_NoMatch(t *testing.T) {
	sr := &stubRunner{
		adminRow:  &db.ServerRow{ID: "admin-1", URL: "http://admin-zoho/mcp"},
		importErr: sql.ErrNoRows,
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, "http://self/mcp")

	_, err := r.Resolve(context.Background(), "charlie@hp.fr", "charlie")
	if !errors.Is(err, ErrNoZohoConfigured) {
		t.Fatalf("err = %v, want ErrNoZohoConfigured", err)
	}
}

func TestResolver_AdminRowMissing(t *testing.T) {
	sr := &stubRunner{adminErr: sql.ErrNoRows}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, "http://self/mcp")

	_, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if !errors.Is(err, ErrMisconfigured) {
		t.Fatalf("err = %v, want ErrMisconfigured", err)
	}
}

func TestResolver_EmptyEmail(t *testing.T) {
	sr := &stubRunner{}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, "http://self/mcp")

	_, err := r.Resolve(context.Background(), "", "")
	if !errors.Is(err, ErrInvalidIdentity) {
		t.Fatalf("err = %v, want ErrInvalidIdentity", err)
	}
}

func TestResolver_CacheHit(t *testing.T) {
	sr := &stubRunner{
		adminRow: &db.ServerRow{ID: "admin-1", URL: "http://admin/mcp"},
		grants:   map[string]map[string]bool{"admin-1": {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, "http://self/mcp")

	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("first Resolve: %v", err)
	}
	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("second Resolve: %v", err)
	}
	if sr.adminCalls > 1 || sr.grantCalls > 1 {
		t.Fatalf("cache miss on second call: admin=%d grant=%d", sr.adminCalls, sr.grantCalls)
	}
}
