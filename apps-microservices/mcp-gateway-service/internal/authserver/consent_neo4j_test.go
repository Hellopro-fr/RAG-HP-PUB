package authserver

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

const gateJWTSecret = "gate-test-secret"

// gateConsentDDL is the minimal schema the consent handlers touch. Hand
// written because the production GORM tags declare datetime(3), which the
// pure-Go SQLite driver does not parse back into time.Time.
var gateConsentDDL = []string{
	`CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
		tool_prefix TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT '', template_slug TEXT NOT NULL DEFAULT '',
		is_active INTEGER NOT NULL DEFAULT 1)`,
	`CREATE TABLE server_tools (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, name TEXT NOT NULL,
		description TEXT NOT NULL DEFAULT '', input_schema BLOB NOT NULL, is_active INTEGER NOT NULL DEFAULT 1)`,
	`CREATE TABLE server_resources (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, uri TEXT NOT NULL, name TEXT NOT NULL DEFAULT '')`,
	`CREATE TABLE server_prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, name TEXT NOT NULL)`,
	`CREATE TABLE prompt_arguments (id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_id INTEGER NOT NULL, name TEXT NOT NULL)`,
	`CREATE TABLE server_tags (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL, tag TEXT NOT NULL)`,
	`CREATE TABLE oauth2_clients (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', redirect_uris TEXT,
		is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL DEFAULT '')`,
	`CREATE TABLE oauth2_client_servers (client_id TEXT NOT NULL, server_id TEXT NOT NULL)`,
	`CREATE TABLE oauth2_client_tools (client_id TEXT NOT NULL, server_id TEXT NOT NULL, tool_name TEXT NOT NULL)`,
	`CREATE TABLE oauth2_client_instructions (client_id TEXT NOT NULL, instruction_id TEXT NOT NULL)`,
	`CREATE TABLE oauth2_client_bdd_tables (client_id TEXT NOT NULL, used_table_id TEXT NOT NULL)`,
	`CREATE TABLE oauth2_consents (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_email TEXT NOT NULL,
		scope TEXT, created_at DATETIME, updated_at DATETIME, UNIQUE (client_id, user_email))`,
	`CREATE TABLE oauth2_authorization_codes (code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_email TEXT NOT NULL,
		redirect_uri TEXT NOT NULL, code_challenge TEXT NOT NULL, scope TEXT, expires_at DATETIME NOT NULL,
		used_at DATETIME, created_at DATETIME)`,
	`INSERT INTO mcp_servers (id, name, url, template_slug) VALUES
		('srv-neo4j', 'Neo4j prod', 'http://neo4j.invalid', 'neo4j'),
		('srv-ga', 'GA4', 'http://ga.invalid', 'ga'),
		('srv-plain', 'Plain', 'http://plain.invalid', '')`,
	`INSERT INTO server_tools (server_id, name, input_schema) VALUES
		('srv-neo4j', 'read_neo4j_cypher', CAST('{}' AS BLOB)),
		('srv-ga', 'run_report', CAST('{}' AS BLOB)),
		('srv-plain', 'echo', CAST('{}' AS BLOB))`,
	`INSERT INTO oauth2_clients (id, name, redirect_uris, created_by) VALUES
		('client-gate', 'gate-client', '["https://client.example.com/callback"]', 'admin@hp.fr')`,
}

// newGateConsentServer builds an AuthServer on a pure-Go in-memory SQLite
// (github.com/glebarez/sqlite: no cgo, so it runs in the Alpine test
// container) seeded with three active servers — a Neo4j instance, a GA4
// instance and a regular server — and one dynamic OAuth2 client (no
// admin-assigned servers). It returns the server, client ID, redirect URI
// and DB handle.
func newGateConsentServer(t *testing.T) (*AuthServer, string, string, *gorm.DB) {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	sqlDB, err := g.DB()
	if err != nil {
		t.Fatalf("sql db: %v", err)
	}
	sqlDB.SetMaxOpenConns(1) // one connection = one in-memory database
	t.Cleanup(func() { _ = sqlDB.Close() })
	for _, stmt := range gateConsentDDL {
		if err := g.Exec(stmt).Error; err != nil {
			t.Fatalf("ddl: %v\n%s", err, stmt)
		}
	}
	s := &AuthServer{
		oauth2Repo:   repository.NewOAuth2Repo(g, nil),
		authCodeRepo: repository.NewAuthCodeRepo(g),
		consentRepo:  repository.NewConsentRepo(g),
		refreshRepo:  repository.NewRefreshRepo(g),
		serverRepo:   repository.NewServerRepo(g, nil),
		jwtSecret:    gateJWTSecret,
		publicURL:    "https://mcp.example.com",
	}
	s.SetServerAccess(newGatePolicy())
	return s, "client-gate", "https://client.example.com/callback", g
}

// sessionCookies returns the mcp_session cookie for email.
func sessionCookies(t *testing.T, s *AuthServer, email string) []*http.Cookie {
	t.Helper()
	rec := httptest.NewRecorder()
	if err := s.mintAuthSession(rec, email, ""); err != nil {
		t.Fatalf("mint session: %v", err)
	}
	return rec.Result().Cookies()
}

func bearerFor(t *testing.T, email string) string {
	t.Helper()
	tok, err := auth.SignJWT(gateJWTSecret, auth.Claims{Email: email, Exp: time.Now().Add(time.Hour).Unix(), Iat: time.Now().Unix()})
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return "Bearer " + tok
}

func authorizeQuery(clientID, redirectURI string) url.Values {
	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")
	return q
}

func storedConsentScope(t *testing.T, g *gorm.DB, clientID, email string) *ConsentScope {
	t.Helper()
	var row db.OAuth2Consent
	if err := g.Where("client_id = ? AND user_email = ?", clientID, email).First(&row).Error; err != nil {
		return nil
	}
	scope, err := ParseConsentScope(row.Scope)
	if err != nil {
		t.Fatalf("parse stored scope: %v", err)
	}
	return scope
}

func TestConsentHTML_HidesNeo4jInstanceFromNonGrantedViewer(t *testing.T) {
	cases := []struct {
		email     string
		wantNeo4j bool
	}{
		{"bob@hp.fr", false},
		{"admin@hp.fr", true},
		{"alice@hp.fr", true},
	}
	for _, tc := range cases {
		t.Run(tc.email, func(t *testing.T) {
			s, clientID, redirectURI, _ := newGateConsentServer(t)
			req := httptest.NewRequest(http.MethodGet, "/authorize?"+authorizeQuery(clientID, redirectURI).Encode(), nil)
			for _, c := range sessionCookies(t, s, tc.email) {
				req.AddCookie(c)
			}
			rec := httptest.NewRecorder()
			s.HandleAuthorize(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("want 200 consent screen, got %d: %s", rec.Code, rec.Body.String())
			}
			body := rec.Body.String()
			if got := strings.Contains(body, `value="srv-neo4j"`); got != tc.wantNeo4j {
				t.Fatalf("%s: srv-neo4j listed=%t, want %t", tc.email, got, tc.wantNeo4j)
			}
			if !strings.Contains(body, `value="srv-plain"`) || !strings.Contains(body, `value="srv-ga"`) {
				t.Fatalf("%s: unrestricted servers must stay listed", tc.email)
			}
		})
	}
}

func TestConsentJSON_HidesNeo4jInstanceFromNonGrantedViewer(t *testing.T) {
	cases := []struct {
		email string
		want  []string
	}{
		{"bob@hp.fr", []string{"srv-ga", "srv-plain"}},
		{"admin@hp.fr", []string{"srv-ga", "srv-neo4j", "srv-plain"}},
		{"alice@hp.fr", []string{"srv-ga", "srv-neo4j", "srv-plain"}},
	}
	for _, tc := range cases {
		t.Run(tc.email, func(t *testing.T) {
			s, clientID, redirectURI, _ := newGateConsentServer(t)
			q := url.Values{}
			q.Set("client_id", clientID)
			q.Set("redirect_uri", redirectURI)
			req := httptest.NewRequest(http.MethodGet, "/api/v1/oauth2/authorize/info?"+q.Encode(), nil)
			req.Header.Set("Authorization", bearerFor(t, tc.email))
			rec := httptest.NewRecorder()
			s.handleAuthorizeInfo(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("want 200, got %d: %s", rec.Code, rec.Body.String())
			}
			var resp authorizeInfoResponse
			if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
				t.Fatalf("decode: %v", err)
			}
			var got []string
			for _, srv := range resp.Servers {
				got = append(got, srv.ID)
			}
			sort.Strings(got)
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("%s: got %v, want %v", tc.email, got, tc.want)
			}
		})
	}
}

func TestConsentHTMLPost_DropsHiddenServer(t *testing.T) {
	s, clientID, redirectURI, g := newGateConsentServer(t)
	form := authorizeQuery(clientID, redirectURI)
	form.Set("action", "consent")
	form.Set("approved", "true")
	form.Set("csrf_token", "csrf-1")
	form["server_ids"] = []string{"srv-neo4j", "srv-plain"}
	req := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.AddCookie(&http.Cookie{Name: "oauth2_csrf", Value: "csrf-1"})
	for _, c := range sessionCookies(t, s, "bob@hp.fr") {
		req.AddCookie(c)
	}
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)
	if rec.Code != http.StatusFound {
		t.Fatalf("want 302 to redirect_uri, got %d: %s", rec.Code, rec.Body.String())
	}
	scope := storedConsentScope(t, g, clientID, "bob@hp.fr")
	if scope == nil || !reflect.DeepEqual(scope.ServerIDs, []string{"srv-plain"}) {
		t.Fatalf("stored consent must keep only srv-plain, got %+v", scope)
	}
}

func TestConsentHTMLPost_OnlyHiddenServersRejected(t *testing.T) {
	s, clientID, redirectURI, g := newGateConsentServer(t)
	form := authorizeQuery(clientID, redirectURI)
	form.Set("action", "consent")
	form.Set("approved", "true")
	form.Set("csrf_token", "csrf-1")
	form["server_ids"] = []string{"srv-neo4j"}
	req := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.AddCookie(&http.Cookie{Name: "oauth2_csrf", Value: "csrf-1"})
	for _, c := range sessionCookies(t, s, "bob@hp.fr") {
		req.AddCookie(c)
	}
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400 when every selected server is hidden, got %d", rec.Code)
	}
	if scope := storedConsentScope(t, g, clientID, "bob@hp.fr"); scope != nil {
		t.Fatalf("nothing must be stored, got %+v", scope)
	}
}

func TestConsentJSONPost_DropsHiddenServerAndTools(t *testing.T) {
	cases := []struct {
		name      string
		auth      string
		userEmail string
	}{
		{"non-granted user", "bob@hp.fr", "bob@hp.fr"},
		{"anonymous fallback", "", "anonymous@client-gate"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s, clientID, redirectURI, g := newGateConsentServer(t)
			body, _ := json.Marshal(authorizeConsentRequest{
				ClientID:            clientID,
				RedirectURI:         redirectURI,
				CodeChallenge:       "abc",
				CodeChallengeMethod: "S256",
				State:               "xyz",
				ServerIDs:           []string{"srv-neo4j", "srv-plain"},
				ToolIDs:             []string{"srv-neo4j:read_neo4j_cypher", "srv-plain:echo"},
			})
			req := httptest.NewRequest(http.MethodPost, "/api/v1/oauth2/authorize/consent", bytes.NewReader(body))
			if tc.auth != "" {
				req.Header.Set("Authorization", bearerFor(t, tc.auth))
			}
			rec := httptest.NewRecorder()
			s.handleAuthorizeConsent(rec, req)
			if rec.Code != http.StatusOK {
				t.Fatalf("want 200, got %d: %s", rec.Code, rec.Body.String())
			}
			scope := storedConsentScope(t, g, clientID, tc.userEmail)
			want := &ConsentScope{
				ServerIDs:   []string{"srv-plain"},
				ServerTools: []ServerToolSelection{{ServerID: "srv-plain", ToolNames: []string{"echo"}}},
			}
			if !reflect.DeepEqual(scope, want) {
				t.Fatalf("stored scope: got %+v, want %+v", scope, want)
			}
		})
	}
}

func TestConsentJSONPost_GranteeKeepsNeo4jInstance(t *testing.T) {
	s, clientID, redirectURI, g := newGateConsentServer(t)
	body, _ := json.Marshal(authorizeConsentRequest{
		ClientID:            clientID,
		RedirectURI:         redirectURI,
		CodeChallenge:       "abc",
		CodeChallengeMethod: "S256",
		ServerIDs:           []string{"srv-neo4j", "srv-plain"},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/oauth2/authorize/consent", bytes.NewReader(body))
	req.Header.Set("Authorization", bearerFor(t, "alice@hp.fr"))
	rec := httptest.NewRecorder()
	s.handleAuthorizeConsent(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", rec.Code, rec.Body.String())
	}
	scope := storedConsentScope(t, g, clientID, "alice@hp.fr")
	if scope == nil || !reflect.DeepEqual(scope.ServerIDs, []string{"srv-neo4j", "srv-plain"}) {
		t.Fatalf("grantee must keep both servers, got %+v", scope)
	}
}
