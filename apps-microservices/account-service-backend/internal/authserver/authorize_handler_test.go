package authserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type fakeAuthCodeRepo struct {
	created *db.OAuth2AuthorizationCode
}

func (f *fakeAuthCodeRepo) Create(c *db.OAuth2AuthorizationCode) error {
	f.created = c
	return nil
}

type fakeClientRepo struct {
	c *db.OAuth2Client
}

func (f *fakeClientRepo) GetByClientID(id string) (*db.OAuth2Client, error) {
	return f.c, nil
}

type fakeUserSrc struct{}

func (fakeUserSrc) UpsertOnLogin(email, name string) (*auth.UpsertedUser, error) {
	return &auth.UpsertedUser{Email: email, IsAllowed: true, IsAdmin: false}, nil
}

func TestAuthorizePOST_LoginIssuesCodeAndRedirects(t *testing.T) {
	uris := `["https://x/cb"]`
	cli := &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris, IsActive: true}

	hellopro := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"success":true,"email":"alice@example.com","display_name":"Alice"}`))
	}))
	defer hellopro.Close()

	srv := NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
		UserUpserter: fakeUserSrc{},
		AuthURL:      hellopro.URL,
		JWTSecret:    "s",
		Issuer:       "https://account.test",
		AuthCodeTTL:  10 * time.Minute,
		SecureCookie: false,
	})

	form := url.Values{
		"action":                {"login"},
		"response_type":         {"code"},
		"client_id":             {"x"},
		"redirect_uri":          {"https://x/cb"},
		"code_challenge":        {"chal"},
		"code_challenge_method": {"S256"},
		"state":                 {"abc"},
		"username":              {"alice"},
		"password":              {"p"},
	}
	r := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)

	if w.Code != http.StatusFound {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	loc := w.Header().Get("Location")
	if !strings.HasPrefix(loc, "https://x/cb?") {
		t.Fatalf("Location=%q", loc)
	}
	q, _ := url.Parse(loc)
	if q.Query().Get("state") != "abc" {
		t.Fatalf("state=%q", q.Query().Get("state"))
	}
	if q.Query().Get("code") == "" {
		t.Fatal("missing code in redirect")
	}
}

func TestAuthorizeGET_BadRedirectURI(t *testing.T) {
	uris := `["https://x/cb"]`
	cli := &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris, IsActive: true}
	srv := NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
	})
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=code&client_id=x&redirect_uri=https://evil/&code_challenge=c&code_challenge_method=S256", nil)
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]string
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["error"] != "invalid_request" {
		t.Fatalf("error=%q", body["error"])
	}
}

func TestAuthorizeGET_NoSession_RedirectsToLoginVue(t *testing.T) {
	uris := `["https://x/cb"]`
	cli := &db.OAuth2Client{ClientID: "x", RedirectURIs: &uris, IsActive: true}
	srv := NewAuthServer(AuthServerDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeAuthCodeRepo{},
		LoginPath:    "/login",
	})
	r := httptest.NewRequest(http.MethodGet, "/authorize?response_type=code&client_id=x&redirect_uri=https://x/cb&code_challenge=c&code_challenge_method=S256&state=abc", nil)
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, r)
	if w.Code != http.StatusFound {
		t.Fatalf("Code=%d", w.Code)
	}
	loc := w.Header().Get("Location")
	if !strings.HasPrefix(loc, "/login?") {
		t.Fatalf("Location=%q", loc)
	}
	if !strings.Contains(loc, "client_id=x") {
		t.Fatalf("client_id missing in %q", loc)
	}
}
