package authserver

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"account-service/internal/auth"
	"account-service/internal/db"
)

// cfgUserSrc is a configurable UserUpserter for exercising the blocked /
// role-not-allowed branches of handleLogin.
type cfgUserSrc struct {
	allowed bool
	admin   bool
}

func (c cfgUserSrc) UpsertOnLogin(email, name string) (*auth.UpsertedUser, error) {
	return &auth.UpsertedUser{Email: email, IsAllowed: c.allowed, IsAdmin: c.admin}, nil
}

func okHelloPro() *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
}

func newTestServer(cli *db.OAuth2Client, helloURL string, users auth.UserUpserter) *AuthServer {
	return NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
		UserUpserter: users,
		AuthURL:      helloURL,
		JWTSecret:    "s",
		Issuer:       "https://account.test",
		LoginPath:    "/login",
		SecureCookie: false,
	})
}

func loginClient() *db.OAuth2Client {
	uris := `["https://x/cb"]`
	return &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris, IsActive: true}
}

func postLogin(srv *AuthServer, username, password string) *httptest.ResponseRecorder {
	form := url.Values{
		"action":                {"login"},
		"response_type":         {"code"},
		"client_id":             {"x"},
		"redirect_uri":          {"https://x/cb"},
		"code_challenge":        {"chal"},
		"code_challenge_method": {"S256"},
		"state":                 {"abc"},
		"username":              {username},
		"password":              {password},
	}
	r := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)
	return w
}

// assertLoginRedirect verifies a 302 back to /login carrying the given error
// code and every OAuth2 param needed to re-render and re-submit the form.
func assertLoginRedirect(t *testing.T, w *httptest.ResponseRecorder, wantErr string) url.Values {
	t.Helper()
	if w.Code != http.StatusFound {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	loc := w.Header().Get("Location")
	if !strings.HasPrefix(loc, "/login?") {
		t.Fatalf("Location=%q want /login? prefix", loc)
	}
	u, err := url.Parse(loc)
	if err != nil {
		t.Fatalf("parse Location %q: %v", loc, err)
	}
	q := u.Query()
	checks := map[string]string{
		"error":                 wantErr,
		"client_id":             "x",
		"redirect_uri":          "https://x/cb",
		"code_challenge":        "chal",
		"code_challenge_method": "S256",
		"response_type":         "code",
		"state":                 "abc",
	}
	for k, want := range checks {
		if q.Get(k) != want {
			t.Fatalf("%s=%q want %q (loc=%s)", k, q.Get(k), want, loc)
		}
	}
	return q
}

func TestAuthorizePOST_BadCredentials_RedirectsToLogin(t *testing.T) {
	hp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":false}`))
	}))
	defer hp.Close()

	srv := newTestServer(loginClient(), hp.URL, cfgUserSrc{allowed: true})
	w := postLogin(srv, "alice", "wrong")

	q := assertLoginRedirect(t, w, "credentials_error")
	if q.Get("username") != "alice" {
		t.Fatalf("username=%q want alice (typed username should survive the bounce)", q.Get("username"))
	}
}

func TestAuthorizePOST_MissingPassword_RedirectsToLogin(t *testing.T) {
	// Missing fields short-circuit before AuthenticateHellopro, so AuthURL is unused.
	srv := newTestServer(loginClient(), "", cfgUserSrc{allowed: true})
	w := postLogin(srv, "alice", "")

	q := assertLoginRedirect(t, w, "missing_credentials")
	if q.Get("username") != "alice" {
		t.Fatalf("username=%q want alice", q.Get("username"))
	}
}

func TestAuthorizePOST_BlockedUser_RedirectsToLogin(t *testing.T) {
	hp := okHelloPro()
	defer hp.Close()

	srv := newTestServer(loginClient(), hp.URL, cfgUserSrc{allowed: false})
	w := postLogin(srv, "alice", "p")

	assertLoginRedirect(t, w, "user_blocked")
}

func TestAuthorizePOST_RoleNotAllowed_RedirectsToLogin(t *testing.T) {
	hp := okHelloPro()
	defer hp.Close()

	cli := loginClient()
	roles := `["admin"]`
	cli.AllowedRoles = &roles

	srv := newTestServer(cli, hp.URL, cfgUserSrc{allowed: true, admin: false})
	w := postLogin(srv, "alice", "p")

	assertLoginRedirect(t, w, "role_not_allowed")
}

// A genuine server error (not a user-fixable login failure) must NOT bounce to
// /login — it stays a JSON error so the problem is visible.
func TestAuthorizePOST_ServerError_StaysJSON(t *testing.T) {
	hp := okHelloPro()
	defer hp.Close()

	srv := newTestServer(loginClient(), hp.URL, errUserSrc{})
	w := postLogin(srv, "alice", "p")

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("Code=%d want 500 (loc=%q)", w.Code, w.Header().Get("Location"))
	}
}

type errUserSrc struct{}

func (errUserSrc) UpsertOnLogin(_, _ string) (*auth.UpsertedUser, error) {
	return nil, http.ErrAbortHandler
}
