package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeSessionRepo struct {
	rows    []db.OAuth2RefreshToken
	revoked string
}

func (f *fakeSessionRepo) ListByUser(email string) ([]db.OAuth2RefreshToken, error) {
	return f.rows, nil
}
func (f *fakeSessionRepo) ListBySID(string) ([]db.OAuth2RefreshToken, error) { return nil, nil }
func (f *fakeSessionRepo) RevokeBySID(sid, reason string) error {
	f.revoked = sid
	return nil
}

func TestSessions_List(t *testing.T) {
	repo := &fakeSessionRepo{rows: []db.OAuth2RefreshToken{{ID: "x", SID: "sid1"}}}
	h := NewSessionsHandler(SessionsDeps{Repo: repo})
	r := httptest.NewRequest(http.MethodGet, "/api/v1/admin/users/alice@x/sessions", nil)
	r.SetPathValue("email", "alice@x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if int(body["total"].(float64)) != 1 {
		t.Errorf("total=%v", body["total"])
	}
}

func TestSessions_RevokeOne(t *testing.T) {
	repo := &fakeSessionRepo{}
	h := NewSessionsHandler(SessionsDeps{Repo: repo})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/sessions/sid1/revoke", nil)
	r.SetPathValue("sid", "sid1")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	if repo.revoked != "sid1" {
		t.Fatal("not revoked")
	}
}
