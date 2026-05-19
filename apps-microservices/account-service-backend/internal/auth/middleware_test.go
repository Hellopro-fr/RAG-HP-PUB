package auth

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRequireAuth_RejectsMissingCookie(t *testing.T) {
	called := false
	h := RequireAuth("secret")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("Code=%d, want 401", w.Code)
	}
	if called {
		t.Fatal("inner handler should not run")
	}
}

func TestRequireAuth_PassesWithValidSession(t *testing.T) {
	w := httptest.NewRecorder()
	_ = SetSession(w, "secret", SessionData{Email: "a@x", Token: "t"}, false)
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	for _, c := range w.Result().Cookies() {
		r.AddCookie(c)
	}

	called := false
	h := RequireAuth("secret")(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
	}))
	h.ServeHTTP(httptest.NewRecorder(), r)
	if !called {
		t.Fatal("inner handler should run")
	}
}

func TestRequireAdmin_RejectsNonAdmin(t *testing.T) {
	w := httptest.NewRecorder()
	_ = SetSession(w, "secret", SessionData{Email: "a@x", Token: "t"}, false)
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	for _, c := range w.Result().Cookies() {
		r.AddCookie(c)
	}
	resolver := func(email string) (bool, bool) { return true, false }
	h := RequireAdmin("secret", resolver)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, r)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("Code=%d, want 403", rr.Code)
	}
}
