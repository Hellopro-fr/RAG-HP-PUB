package auth

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSetGetSessionRoundTrip(t *testing.T) {
	w := httptest.NewRecorder()
	data := SessionData{Email: "alice@example.com", DisplayName: "Alice", Token: "tok"}
	if err := SetSession(w, "secret", data, false); err != nil {
		t.Fatalf("SetSession: %v", err)
	}

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	for _, c := range w.Result().Cookies() {
		r.AddCookie(c)
	}
	got, err := GetSession(r, "secret")
	if err != nil {
		t.Fatalf("GetSession: %v", err)
	}
	if got.Email != "alice@example.com" {
		t.Errorf("Email=%q", got.Email)
	}
}

func TestClearSessionExpires(t *testing.T) {
	w := httptest.NewRecorder()
	ClearSession(w)
	cookies := w.Result().Cookies()
	if len(cookies) == 0 {
		t.Fatal("no cookie set")
	}
	if cookies[0].MaxAge >= 0 {
		t.Fatalf("MaxAge=%d, want <0", cookies[0].MaxAge)
	}
}
