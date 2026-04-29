package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const testSecret = "test-jwt-secret"

func mintToken(t *testing.T, claims jwt.MapClaims) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	s, err := tok.SignedString([]byte(testSecret))
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestJWT_ValidToken(t *testing.T) {
	tok := mintToken(t, jwt.MapClaims{"role": "admin", "exp": time.Now().Add(time.Hour).Unix()})
	called := false
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		u := UserFromContext(r.Context())
		if u == nil || u["role"] != "admin" {
			t.Errorf("missing claims: %v", u)
		}
		w.WriteHeader(200)
	}))
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer "+tok)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if !called {
		t.Error("inner handler not called")
	}
	if w.Code != 200 {
		t.Errorf("status=%d", w.Code)
	}
}

func TestJWT_NoHeader(t *testing.T) {
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("must not be called") }))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	h.ServeHTTP(w, r)
	if w.Code != 401 {
		t.Errorf("status=%d, want 401", w.Code)
	}
}

func TestJWT_BadToken(t *testing.T) {
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("must not be called") }))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer not.a.token")
	h.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Errorf("status=%d, want 403", w.Code)
	}
}

func TestJWT_ExpiredToken(t *testing.T) {
	tok := mintToken(t, jwt.MapClaims{"role": "admin", "exp": time.Now().Add(-time.Hour).Unix()})
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("must not be called") }))
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer "+tok)
	h.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Errorf("status=%d, want 403", w.Code)
	}
}

func TestJWT_NodeInteropHS256(t *testing.T) {
	// Vérifie qu'un token signé avec la même secret par jsonwebtoken Node
	// (HS256) serait accepté. On simule en re-signant côté Go avec la même clé.
	// Si on a accès à node + jsonwebtoken, on peut générer un token réel et le coller ici.
	tok := mintToken(t, jwt.MapClaims{
		"role": "admin",
		"iat":  time.Now().Unix(),
		"exp":  time.Now().Add(24 * time.Hour).Unix(),
	})
	h := JWTAuth(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	r := httptest.NewRequest("GET", "/x", nil)
	r.Header.Set("Authorization", "Bearer "+tok)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Errorf("HS256 24h token rejected: %d", w.Code)
	}
}
