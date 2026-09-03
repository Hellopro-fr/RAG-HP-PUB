package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestSecurityHeaders(t *testing.T) {
	h := SecurityHeaders(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Header().Get("X-Frame-Options") != "DENY" {
		t.Errorf("X-Frame-Options = %q", w.Header().Get("X-Frame-Options"))
	}
	if w.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Errorf("X-Content-Type-Options = %q", w.Header().Get("X-Content-Type-Options"))
	}
	if w.Header().Get("Referrer-Policy") != "no-referrer" {
		t.Errorf("Referrer-Policy = %q", w.Header().Get("Referrer-Policy"))
	}
}

func TestRateLimit_429AfterMax(t *testing.T) {
	mw := RateLimitByIP(2, time.Minute)
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))

	for i := 0; i < 2; i++ {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/", nil)
		r.RemoteAddr = "127.0.0.1:1234"
		h.ServeHTTP(w, r)
		if w.Code != 200 {
			t.Errorf("call %d: status=%d", i, w.Code)
		}
	}
	w := httptest.NewRecorder()
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "127.0.0.1:1234"
	h.ServeHTTP(w, r)
	if w.Code != 429 {
		t.Errorf("3rd call: status=%d, want 429", w.Code)
	}
}

// TestRateLimit_ForgedHeaderCannotBypass : depuis une IP publique (service
// expose sans proxy), un X-Real-IP invente ne doit pas ouvrir un seau neuf.
func TestRateLimit_ForgedHeaderCannotBypass(t *testing.T) {
	mw := RateLimitByIP(1, time.Minute)
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))

	w1 := httptest.NewRecorder()
	r1 := httptest.NewRequest("GET", "/", nil)
	r1.RemoteAddr = "203.0.113.7:5555"
	h.ServeHTTP(w1, r1)
	if w1.Code != 200 {
		t.Fatalf("1re requete: status=%d, want 200", w1.Code)
	}

	w2 := httptest.NewRecorder()
	r2 := httptest.NewRequest("GET", "/", nil)
	r2.RemoteAddr = "203.0.113.7:5556"
	r2.Header.Set("X-Real-IP", "10.1.2.3")
	r2.Header.Set("X-Forwarded-For", "10.1.2.3")
	h.ServeHTTP(w2, r2)
	if w2.Code != 429 {
		t.Errorf("en-tete forge: status=%d, want 429 (meme seau)", w2.Code)
	}
}

// TestRateLimit_TrustedProxyHeaderHonored : derriere nginx (IP privee), deux
// clients distincts ne partagent pas le quota.
func TestRateLimit_TrustedProxyHeaderHonored(t *testing.T) {
	mw := RateLimitByIP(1, time.Minute)
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))

	for _, real := range []string{"203.0.113.1", "203.0.113.2"} {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/", nil)
		r.RemoteAddr = "172.18.0.5:5555"
		r.Header.Set("X-Real-IP", real)
		h.ServeHTTP(w, r)
		if w.Code != 200 {
			t.Errorf("client %s: status=%d, want 200", real, w.Code)
		}
	}
}

func TestCORS_DefaultWildcard(t *testing.T) {
	mw := CORS(nil)
	h := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	r := httptest.NewRequest("OPTIONS", "/", nil)
	r.Header.Set("Origin", "https://anywhere.example")
	r.Header.Set("Access-Control-Request-Method", "GET")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if got := w.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Errorf("Allow-Origin = %q, want *", got)
	}
}
