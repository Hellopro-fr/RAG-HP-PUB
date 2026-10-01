package sso

import (
	"net/http/httptest"
	"testing"
)

func TestNewSessionID(t *testing.T) {
	a, err := NewSessionID()
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	b, err := NewSessionID()
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if a == b {
		t.Fatal("ids must be unique")
	}
	if len(a) != 64 {
		t.Fatalf("hex(32) want 64 chars got %d", len(a))
	}
}

func TestSessionCookieRoundTrip(t *testing.T) {
	w := httptest.NewRecorder()
	SetSessionCookie(w, "abc123", false)

	req := httptest.NewRequest("GET", "/", nil)
	for _, c := range w.Result().Cookies() {
		req.AddCookie(c)
	}
	got, err := GetSessionID(req)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if got != "abc123" {
		t.Fatalf("got %q want abc123", got)
	}
}

func TestClearSessionCookie(t *testing.T) {
	w := httptest.NewRecorder()
	ClearSessionCookie(w, false)
	cookies := w.Result().Cookies()
	if len(cookies) == 0 {
		t.Fatal("expected Set-Cookie")
	}
	if cookies[0].MaxAge != -1 {
		t.Fatalf("expected MaxAge=-1, got %d", cookies[0].MaxAge)
	}
}
