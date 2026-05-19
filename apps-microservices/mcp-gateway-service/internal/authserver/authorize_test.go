package authserver

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/sso"
)

func TestHandleAuthorize_MissingParams(t *testing.T) {
	srv := &AuthServer{publicURL: "https://mcp.example.com"}
	req := httptest.NewRequest("GET", "/authorize", nil)
	w := httptest.NewRecorder()
	srv.HandleAuthorize(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

// fakeSSORepo is a minimal stand-in for *repository.SSOSessionRepo that lets
// authserver tests verify bridge logic without a real GORM stack. Only
// FindByID is exercised by showLoginOrConsent.
type fakeSSORepo struct {
	rows map[string]*db.SSOSession
}

func (f *fakeSSORepo) FindByID(id string) (*db.SSOSession, error) {
	row, ok := f.rows[id]
	if !ok {
		return nil, errors.New("not found")
	}
	return row, nil
}

// setupAuthorizeTestDB spins up an in-memory sqlite DB with just the tables
// needed to exercise GET /authorize: oauth2_clients, mcp_servers, and
// oauth2_consents. Schema is hand-written because the production GORM tags
// use MySQL-only types.
func setupAuthorizeTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	dsn := "file:" + t.Name() + "?mode=memory&cache=private&_foreign_keys=on"
	g, err := gorm.Open(sqlite.Open(dsn), &gorm.Config{
		Logger:               logger.Default.LogMode(logger.Silent),
		DisableAutomaticPing: true,
	})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	stmts := []string{
		`CREATE TABLE oauth2_clients (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			secret_hash TEXT NOT NULL,
			secret_prefix TEXT NOT NULL DEFAULT '',
			encrypted_secret BLOB,
			redirect_uris TEXT,
			grant_types TEXT,
			token_auth_method TEXT NOT NULL DEFAULT 'client_secret_post',
			dynamically_registered INTEGER NOT NULL DEFAULT 0,
			access_token_ttl INTEGER NOT NULL DEFAULT 3600,
			expires_at DATETIME,
			is_active INTEGER NOT NULL DEFAULT 1,
			created_by TEXT NOT NULL DEFAULT '',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			leexi_filter_mode TEXT NOT NULL DEFAULT 'none',
			leexi_allowed_user_uuids TEXT,
			leexi_allowed_team_uuids TEXT,
			ringover_filter_mode TEXT NOT NULL DEFAULT 'none',
			ringover_allowed_user_ids TEXT,
			ringover_allowed_team_ids TEXT,
			zoho_filter_mode TEXT NOT NULL DEFAULT 'none',
			zoho_allowed_emails TEXT
		)`,
		`CREATE TABLE oauth2_client_servers (
			client_id TEXT NOT NULL,
			server_id TEXT NOT NULL,
			PRIMARY KEY (client_id, server_id)
		)`,
		`CREATE TABLE oauth2_client_tools (
			client_id TEXT NOT NULL,
			server_id TEXT NOT NULL,
			tool_name TEXT NOT NULL,
			PRIMARY KEY (client_id, server_id, tool_name)
		)`,
		`CREATE TABLE oauth2_client_bdd_tables (
			client_id TEXT NOT NULL,
			used_table_id TEXT NOT NULL,
			PRIMARY KEY (client_id, used_table_id)
		)`,
		`CREATE TABLE oauth2_client_instructions (
			client_id TEXT NOT NULL,
			instruction_id TEXT NOT NULL,
			PRIMARY KEY (client_id, instruction_id)
		)`,
		`CREATE TABLE oauth2_consents (
			id TEXT PRIMARY KEY,
			client_id TEXT NOT NULL,
			user_email TEXT NOT NULL,
			scope TEXT NOT NULL DEFAULT '',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE mcp_servers (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			url TEXT NOT NULL DEFAULT '',
			message_url TEXT NOT NULL DEFAULT '',
			transport_type TEXT NOT NULL DEFAULT '',
			tool_prefix TEXT NOT NULL DEFAULT '',
			server_name TEXT NOT NULL DEFAULT '',
			server_version TEXT NOT NULL DEFAULT '',
			capabilities_raw BLOB,
			auth_headers BLOB,
			is_active INTEGER NOT NULL DEFAULT 1,
			health_status TEXT NOT NULL DEFAULT '',
			last_checked DATETIME,
			last_healthy_at DATETIME,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE server_tools (
			server_id TEXT NOT NULL,
			name TEXT NOT NULL,
			description TEXT NOT NULL DEFAULT '',
			input_schema TEXT NOT NULL DEFAULT '',
			is_active INTEGER NOT NULL DEFAULT 1,
			PRIMARY KEY (server_id, name)
		)`,
		`CREATE TABLE server_resources (
			server_id TEXT NOT NULL,
			uri TEXT NOT NULL,
			name TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			mime_type TEXT NOT NULL DEFAULT '',
			PRIMARY KEY (server_id, uri)
		)`,
		`CREATE TABLE server_prompts (
			id TEXT PRIMARY KEY,
			server_id TEXT NOT NULL,
			name TEXT NOT NULL,
			description TEXT NOT NULL DEFAULT ''
		)`,
		`CREATE TABLE prompt_arguments (
			prompt_id TEXT NOT NULL,
			name TEXT NOT NULL,
			description TEXT NOT NULL DEFAULT '',
			is_required INTEGER NOT NULL DEFAULT 0,
			PRIMARY KEY (prompt_id, name)
		)`,
		`CREATE TABLE server_tags (
			server_id TEXT NOT NULL,
			tag TEXT NOT NULL,
			PRIMARY KEY (server_id, tag)
		)`,
	}
	for _, s := range stmts {
		if err := g.Exec(s).Error; err != nil {
			t.Fatalf("ddl: %v\n%s", err, s)
		}
	}
	t.Cleanup(func() {
		sqlDB, err := g.DB()
		if err == nil {
			_ = sqlDB.Close()
		}
	})
	return g
}

// newTestAuthServer wires an AuthServer against the in-memory test DB. The
// SSO session bridge is left nil — tests that exercise tier 2 set
// ssoSessionRepo explicitly.
func newTestAuthServer(t *testing.T) *AuthServer {
	t.Helper()
	g := setupAuthorizeTestDB(t)
	return &AuthServer{
		oauth2Repo:   repository.NewOAuth2Repo(g, nil),
		authCodeRepo: repository.NewAuthCodeRepo(g),
		consentRepo:  repository.NewConsentRepo(g),
		refreshRepo:  repository.NewRefreshRepo(g),
		serverRepo:   repository.NewServerRepo(g, nil),
		jwtSecret:    "test-secret-please-change",
		publicURL:    "https://mcp.example.com",
		secureCookie: false,
		refreshTTL:   3600,
	}
}

// seedTestOAuth2Client persists a minimal OAuth2 client with one registered
// redirect_uri and returns (clientID, redirectURI).
func seedTestOAuth2Client(t *testing.T, s *AuthServer) (string, string) {
	t.Helper()
	clientID := uuid.NewString()
	redirectURI := "https://client.example.com/callback"
	urisJSON, _ := json.Marshal([]string{redirectURI})
	uris := string(urisJSON)
	cl := db.OAuth2Client{
		ID:           clientID,
		Name:         "test-client",
		SecretHash:   "hash-" + clientID,
		RedirectURIs: &uris,
	}
	if err := s.oauth2Repo.Create(&cl); err != nil {
		t.Fatalf("seed oauth2 client: %v", err)
	}
	return clientID, redirectURI
}

func TestHandleAuthorize_NoSessionRedirectsToSSOLoginWithOAuth2Purpose(t *testing.T) {
	// Tier 3: no mcp_session, no gw_session bridge → 303 to /sso/login.
	s := newTestAuthServer(t) // bridge disabled (ssoSessionRepo nil)
	clientID, redirectURI := seedTestOAuth2Client(t, s)

	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")

	req := httptest.NewRequest(http.MethodGet, "/authorize?"+q.Encode(), nil)
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d (body: %s)", rec.Code, rec.Body.String())
	}
	loc := rec.Header().Get("Location")
	parsed, err := url.Parse(loc)
	if err != nil {
		t.Fatalf("url.Parse: %v", err)
	}
	if !strings.HasPrefix(parsed.Path, "/sso/login") {
		t.Fatalf("expected redirect to /sso/login, got %q", loc)
	}
	if got := parsed.Query().Get("purpose"); got != "oauth2" {
		t.Fatalf("expected purpose=oauth2, got %q", got)
	}
	if !strings.HasPrefix(parsed.Query().Get("return_to"), "/authorize?") {
		t.Fatalf("return_to should round-trip the original /authorize URL, got %q", parsed.Query().Get("return_to"))
	}
}

func TestHandleAuthorize_BridgesGwSessionToMcpSession(t *testing.T) {
	// Tier 2: valid gw_session pointing to non-expired sso_sessions row →
	// consent rendered, mcp_session minted.
	s := newTestAuthServer(t)
	s.ssoSessionRepo = &fakeSSORepo{rows: map[string]*db.SSOSession{
		"sid-1": {ID: "sid-1", Email: "alice@example.com", AccessExp: time.Now().Add(time.Hour)},
	}}
	clientID, redirectURI := seedTestOAuth2Client(t, s)

	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")

	req := httptest.NewRequest(http.MethodGet, "/authorize?"+q.Encode(), nil)
	req.AddCookie(&http.Cookie{Name: sso.CookieName, Value: "sid-1"})
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 (consent screen), got %d (body: %s)", rec.Code, rec.Body.String())
	}
	var sawMcp bool
	for _, c := range rec.Result().Cookies() {
		if c.Name == "mcp_session" {
			sawMcp = true
		}
	}
	if !sawMcp {
		t.Fatal("expected mcp_session cookie minted on bridge")
	}
}

func TestHandleAuthorize_BridgeIgnoresExpiredSSOSession(t *testing.T) {
	// Expired SSO row → falls through to tier 3 (redirect).
	s := newTestAuthServer(t)
	s.ssoSessionRepo = &fakeSSORepo{rows: map[string]*db.SSOSession{
		"sid-expired": {ID: "sid-expired", Email: "alice@example.com", AccessExp: time.Now().Add(-time.Hour)},
	}}
	clientID, redirectURI := seedTestOAuth2Client(t, s)

	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")

	req := httptest.NewRequest(http.MethodGet, "/authorize?"+q.Encode(), nil)
	req.AddCookie(&http.Cookie{Name: sso.CookieName, Value: "sid-expired"})
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303 (expired bridge falls through), got %d", rec.Code)
	}
	if !strings.HasPrefix(rec.Header().Get("Location"), "/sso/login") {
		t.Fatalf("expected redirect to /sso/login, got %q", rec.Header().Get("Location"))
	}
}
