package authserver

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"account-service/internal/db"
)

type fakeClientLookup struct {
	out *db.OAuth2Client
	err error
}

func (f fakeClientLookup) GetByClientID(id string) (*db.OAuth2Client, error) {
	if f.err != nil {
		return nil, f.err
	}
	return f.out, nil
}

func TestBrandingHandler_ReturnsPublicFields(t *testing.T) {
	cli := &db.OAuth2Client{ClientID: "x", Name: "Hellopro X", LogoURL: "/u/x.png", BrandColor: "#0055ff"}
	h := NewBrandingHandler(fakeClientLookup{out: cli})

	r := httptest.NewRequest(http.MethodGet, "/authorize/branding/x", nil)
	r.SetPathValue("client_id", "x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["name"] != "Hellopro X" || got["logo_url"] != "/u/x.png" || got["brand_color"] != "#0055ff" {
		t.Fatalf("unexpected body: %v", got)
	}
}

func TestBrandingHandler_404OnUnknownClient(t *testing.T) {
	h := NewBrandingHandler(fakeClientLookup{err: errors.New("not found")})
	r := httptest.NewRequest(http.MethodGet, "/authorize/branding/x", nil)
	r.SetPathValue("client_id", "x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusNotFound {
		t.Fatalf("Code=%d", w.Code)
	}
}
