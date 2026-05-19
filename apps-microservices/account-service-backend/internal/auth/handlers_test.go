package auth

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

type fakeUserRepo struct {
	upsertCalled bool
	isAdmin      bool
	isAllowed    bool
}

func (f *fakeUserRepo) UpsertOnLogin(email, name string) (*UpsertedUser, error) {
	f.upsertCalled = true
	return &UpsertedUser{Email: email, IsAdmin: f.isAdmin, IsAllowed: f.isAllowed}, nil
}

func TestHandleLogin_RoundTripJSON(t *testing.T) {
	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
	defer hellopro.Close()

	cfg := Config{
		AuthURL:   hellopro.URL,
		JWTSecret: "secret",
	}
	repo := &fakeUserRepo{isAllowed: true, isAdmin: true}

	h := NewLoginHandler(cfg, repo)
	body, _ := json.Marshal(map[string]string{"username": "alice", "password": "p"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var out map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &out)
	if out["email"] != "alice@example.com" {
		t.Errorf("email=%v", out["email"])
	}
	if out["is_admin"] != true {
		t.Errorf("is_admin=%v", out["is_admin"])
	}
	if !repo.upsertCalled {
		t.Fatal("upsert not called")
	}
}

func TestHandleLogin_InvalidCredentials(t *testing.T) {
	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":false}`))
	}))
	defer hellopro.Close()

	cfg := Config{AuthURL: hellopro.URL, JWTSecret: "s"}
	h := NewLoginHandler(cfg, &fakeUserRepo{})
	body, _ := json.Marshal(map[string]string{"username": "alice", "password": "bad"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Fatalf("Code=%d", w.Code)
	}
}

func TestHandleLogin_BlockedUser(t *testing.T) {
	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"a@x","display_name":"A"}`))
	}))
	defer hellopro.Close()

	cfg := Config{AuthURL: hellopro.URL, JWTSecret: "s"}
	repo := &fakeUserRepo{isAllowed: false}
	h := NewLoginHandler(cfg, repo)
	body, _ := json.Marshal(map[string]string{"username": "a", "password": "p"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusForbidden {
		t.Fatalf("Code=%d", w.Code)
	}
}
