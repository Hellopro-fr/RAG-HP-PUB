package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"account-service/internal/db"
)

func TestAdminServices_RotateSecret(t *testing.T) {
	repo := &fakeServiceRepo{
		clients: []db.OAuth2Client{{ID: "id-1", ClientID: "cli-1", Name: "Example", ClientSecretEnc: []byte("ENC:old")}},
	}
	h := NewAdminServiceDetailHandler(AdminServiceDetailDeps{
		Repo:    repo,
		Encrypt: func(p []byte) ([]byte, error) { return append([]byte("ENC:"), p...), nil },
	})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/services/id-1/rotate-secret", nil)
	r.SetPathValue("id", "id-1")
	r.SetPathValue("op", "rotate-secret")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["client_secret"] == "" {
		t.Fatal("missing client_secret in response")
	}
}

func TestAdminServices_Update(t *testing.T) {
	repo := &fakeServiceRepo{
		clients: []db.OAuth2Client{{ID: "id-1", Name: "Old"}},
	}
	h := NewAdminServiceDetailHandler(AdminServiceDetailDeps{Repo: repo})
	body, _ := json.Marshal(map[string]interface{}{"name": "New"})
	r := httptest.NewRequest(http.MethodPut, "/api/v1/admin/services/id-1", bytes.NewReader(body))
	r.SetPathValue("id", "id-1")
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	if repo.clients[0].Name != "New" {
		t.Fatalf("name=%q", repo.clients[0].Name)
	}
}
