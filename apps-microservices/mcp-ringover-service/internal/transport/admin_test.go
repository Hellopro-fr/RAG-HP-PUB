package transport

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAdminAuthorized(t *testing.T) {
	cases := []struct {
		name   string
		token  string
		header string
		want   bool
	}{
		{"empty token disables endpoint", "", "", false},
		{"empty token rejects any header", "", "anything", false},
		{"matching token", "secret", "secret", true},
		{"mismatched length", "secret", "secrets", false},
		{"mismatched value", "secret", "public", false},
		{"empty header", "secret", "", false},
	}
	for _, c := range cases {
		s := &AdminServer{token: []byte(c.token)}
		r := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
		if c.header != "" {
			r.Header.Set(AdminTokenHeader, c.header)
		}
		if got := s.authorized(r); got != c.want {
			t.Errorf("%s: authorized=%v, want %v", c.name, got, c.want)
		}
	}
}

func TestAdminHandleUsersUnauthorized(t *testing.T) {
	s := &AdminServer{token: []byte("secret")}
	rr := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
	s.handleUsers(rr, r)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}

func TestAdminHandleUsersMethodNotAllowed(t *testing.T) {
	s := &AdminServer{token: []byte("secret")}
	rr := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodPost, "/admin/users", nil)
	s.handleUsers(rr, r)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405, got %d", rr.Code)
	}
}
