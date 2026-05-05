package authserver

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"account-service/internal/db"
)

type fakeClientCreator struct {
	created *db.OAuth2Client
}

func (f *fakeClientCreator) Create(c *db.OAuth2Client) error {
	c.ID = "id-1"
	f.created = c
	return nil
}

func TestRegister_CreatesClientReturnsSecretOnce(t *testing.T) {
	c := &fakeClientCreator{}
	h := NewRegisterHandler(RegisterDeps{
		Creator: c,
		Encrypt: func(plain []byte) ([]byte, error) { return append([]byte("ENC:"), plain...), nil },
	})
	body, _ := json.Marshal(map[string]interface{}{
		"client_name":   "Example",
		"redirect_uris": []string{"https://x/cb"},
	})
	r := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusCreated {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["client_id"] == "" || got["client_secret"] == "" {
		t.Fatalf("missing client_id/secret: %v", got)
	}
	if c.created.Name != "Example" {
		t.Errorf("Name=%q", c.created.Name)
	}
}
