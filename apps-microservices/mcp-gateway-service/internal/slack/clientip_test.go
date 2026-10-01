package slack

import (
	"net/http/httptest"
	"testing"
)

func TestClientIP_StripsPort(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "203.0.113.5:5432"
	if got := ClientIP(r); got != "203.0.113.5" {
		t.Fatalf("got %q, want 203.0.113.5", got)
	}
}

func TestClientIP_IPv6WithPort(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "[2001:db8::1]:5432"
	if got := ClientIP(r); got != "2001:db8::1" {
		t.Fatalf("got %q, want 2001:db8::1", got)
	}
}

func TestClientIP_ForwardedForFirst(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "10.0.0.1:12345"
	r.Header.Set("X-Forwarded-For", "203.0.113.5, 10.0.0.1")
	if got := ClientIP(r); got != "203.0.113.5" {
		t.Fatalf("got %q, want 203.0.113.5", got)
	}
}

func TestClientIP_NoPort(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "127.0.0.1"
	if got := ClientIP(r); got != "127.0.0.1" {
		t.Fatalf("got %q, want 127.0.0.1", got)
	}
}

func TestClientIP_ForwardedForSingle(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "10.0.0.1:12345"
	r.Header.Set("X-Forwarded-For", "203.0.113.5")
	if got := ClientIP(r); got != "203.0.113.5" {
		t.Fatalf("got %q, want 203.0.113.5", got)
	}
}
