package routing

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"mcp-zoho-service/internal/db"
)

type stubRunner struct {
	adminRow    *db.ImportRow
	adminErr    error
	importRow   *db.ImportRow
	importErr   error
	grants      map[string]map[string]bool // stubID → email(lower) → granted
	adminCalls  int
	grantCalls  int
	importCalls int
}

func (s *stubRunner) FindAdminZohoImport(_ context.Context) (*db.ImportRow, error) {
	s.adminCalls++
	if s.adminErr != nil {
		return nil, s.adminErr
	}
	if s.adminRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.adminRow, nil
}

func (s *stubRunner) IsAdminGranted(_ context.Context, stubID, email string) (bool, error) {
	s.grantCalls++
	g, ok := s.grants[stubID]
	if !ok {
		return false, nil
	}
	return g[lower(email)], nil
}

func (s *stubRunner) FindUserZohoImport(_ context.Context, _, _ string) (*db.ImportRow, error) {
	s.importCalls++
	if s.importErr != nil {
		return nil, s.importErr
	}
	if s.importRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.importRow, nil
}

type fakeDecryptor struct{}

func (fakeDecryptor) Decrypt(b []byte) ([]byte, error) { return b, nil }

const testStubID = "stub-uuid-1234"

func TestResolver_AdminGranted(t *testing.T) {
	sr := &stubRunner{
		adminRow: &db.ImportRow{ID: "admin-1", URL: "http://admin-zoho/mcp", AuthHeaders: []byte(`{"Authorization":"Bearer admin"}`), IsAdmin: true},
		grants:   map[string]map[string]bool{testStubID: {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://admin-zoho/mcp" {
		t.Fatalf("upstream = %q", got.UpstreamURL)
	}
	if got.Headers["Authorization"] != "Bearer admin" {
		t.Fatalf("Authorization = %q", got.Headers["Authorization"])
	}
}

func TestResolver_AdminGrantedButNoAdminRow(t *testing.T) {
	sr := &stubRunner{
		grants: map[string]map[string]bool{testStubID: {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	_, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if !errors.Is(err, ErrNoAdminZohoConfigured) {
		t.Fatalf("err = %v, want ErrNoAdminZohoConfigured", err)
	}
}

func TestResolver_UserImport(t *testing.T) {
	sr := &stubRunner{
		grants:    map[string]map[string]bool{},
		importRow: &db.ImportRow{ID: "user-1", URL: "http://alice-zoho/mcp", CreatedBy: "alice@hp.fr"},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	got, err := r.Resolve(context.Background(), "alice@hp.fr", "alice")
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if got.UpstreamURL != "http://alice-zoho/mcp" {
		t.Fatalf("upstream = %q", got.UpstreamURL)
	}
}

func TestResolver_NoMatch(t *testing.T) {
	sr := &stubRunner{importErr: sql.ErrNoRows}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	_, err := r.Resolve(context.Background(), "charlie@hp.fr", "charlie")
	if !errors.Is(err, ErrNoZohoConfigured) {
		t.Fatalf("err = %v, want ErrNoZohoConfigured", err)
	}
}

func TestResolver_EmptyEmail(t *testing.T) {
	sr := &stubRunner{}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	_, err := r.Resolve(context.Background(), "", "")
	if !errors.Is(err, ErrInvalidIdentity) {
		t.Fatalf("err = %v, want ErrInvalidIdentity", err)
	}
}

func TestResolver_CacheHit(t *testing.T) {
	sr := &stubRunner{
		adminRow: &db.ImportRow{ID: "admin-1", URL: "http://admin/mcp"},
		grants:   map[string]map[string]bool{testStubID: {"alice@hp.fr": true}},
	}
	r := NewResolver(sr, fakeDecryptor{}, time.Minute, testStubID)

	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("first: %v", err)
	}
	if _, err := r.Resolve(context.Background(), "alice@hp.fr", "alice"); err != nil {
		t.Fatalf("second: %v", err)
	}
	if sr.adminCalls > 1 || sr.grantCalls > 1 {
		t.Fatalf("cache miss on second call: admin=%d grant=%d", sr.adminCalls, sr.grantCalls)
	}
}
