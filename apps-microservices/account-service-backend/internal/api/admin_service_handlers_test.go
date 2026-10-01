package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"account-service/internal/db"
)

var errNotFound = errors.New("not found")

type fakeServiceRepo struct {
	clients []db.OAuth2Client
	created *db.OAuth2Client
}

func (f *fakeServiceRepo) Create(c *db.OAuth2Client) error {
	c.ID = "id-1"
	f.created = c
	f.clients = append(f.clients, *c)
	return nil
}
func (f *fakeServiceRepo) GetByID(id string) (*db.OAuth2Client, error) {
	for i := range f.clients {
		if f.clients[i].ID == id {
			return &f.clients[i], nil
		}
	}
	return nil, errNotFound
}
func (f *fakeServiceRepo) GetByClientID(string) (*db.OAuth2Client, error) { return nil, errNotFound }
func (f *fakeServiceRepo) Update(id string, fields map[string]interface{}) error {
	for i := range f.clients {
		if f.clients[i].ID == id {
			if v, ok := fields["name"]; ok {
				f.clients[i].Name = v.(string)
			}
			return nil
		}
	}
	return errNotFound
}
func (f *fakeServiceRepo) Delete(string) error { return nil }
func (f *fakeServiceRepo) List(int, int) ([]db.OAuth2Client, int64, error) {
	return f.clients, int64(len(f.clients)), nil
}

func TestAdminServices_CreateReturnsSecretOnce(t *testing.T) {
	repo := &fakeServiceRepo{}
	h := NewAdminServiceHandler(AdminServiceDeps{
		Repo:    repo,
		Encrypt: func(p []byte) ([]byte, error) { return append([]byte("ENC:"), p...), nil },
	})
	body, _ := json.Marshal(map[string]interface{}{
		"name":          "Example",
		"redirect_uris": []string{"https://x/cb"},
	})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/services", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusCreated {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["client_id"] == "" || got["client_secret"] == "" {
		t.Fatalf("missing fields: %v", got)
	}
}

func TestAdminServices_List(t *testing.T) {
	repo := &fakeServiceRepo{
		clients: []db.OAuth2Client{{ID: "id-1", Name: "Example"}},
	}
	h := NewAdminServiceHandler(AdminServiceDeps{
		Repo:    repo,
		Encrypt: func(p []byte) ([]byte, error) { return p, nil },
	})
	r := httptest.NewRequest(http.MethodGet, "/api/v1/admin/services", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if int(got["total"].(float64)) != 1 {
		t.Errorf("total=%v", got["total"])
	}
}
