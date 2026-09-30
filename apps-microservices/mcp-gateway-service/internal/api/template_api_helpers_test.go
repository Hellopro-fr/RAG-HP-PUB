package api

import (
	"bytes"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/config"
	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/runnerclient"
)

// Same hand-rolled DDL as internal/repository/template_repo_test.go
// (newTemplateTestDB), including the runner column.
const templateAPITestDDL = `
	CREATE TABLE templates (
		slug                TEXT PRIMARY KEY,
		name                TEXT NOT NULL,
		description         TEXT,
		icon                TEXT NOT NULL DEFAULT '',
		stdio_command       TEXT NOT NULL,
		stdio_args          TEXT,
		default_env         TEXT,
		required_extra_env  TEXT,
		tool_prefix         TEXT NOT NULL DEFAULT '',
		tags                TEXT,
		is_active           INTEGER NOT NULL DEFAULT 1,
		kind                TEXT NOT NULL DEFAULT 'stdio',
		runner              TEXT NOT NULL DEFAULT 'google',
		created_at          datetime,
		updated_at          datetime
	);
	CREATE TABLE mcp_servers (
		id                   TEXT PRIMARY KEY,
		name                 TEXT NOT NULL DEFAULT '',
		url                  TEXT NOT NULL DEFAULT '',
		transport_preference TEXT NOT NULL DEFAULT 'auto',
		connect_timeout_ms   INTEGER NOT NULL DEFAULT 10000,
		mcp_transport        TEXT NOT NULL DEFAULT 'http',
		tool_prefix          TEXT NOT NULL DEFAULT '',
		icon                 TEXT NOT NULL DEFAULT '',
		template_slug        TEXT NOT NULL DEFAULT '',
		doc_slug             TEXT,
		is_active            INTEGER NOT NULL DEFAULT 1,
		health_status        TEXT NOT NULL DEFAULT 'unknown',
		created_by           TEXT NOT NULL DEFAULT '',
		created_at           datetime,
		updated_at           datetime
	);
	CREATE TABLE template_instances (
		id                    TEXT PRIMARY KEY,
		template_slug         TEXT NOT NULL,
		name                  TEXT NOT NULL,
		encrypted_credentials BLOB NOT NULL,
		credentials_hash      TEXT NOT NULL,
		extra_env             TEXT,
		runner_port           INTEGER,
		runner_status         TEXT NOT NULL DEFAULT 'pending',
		runner_last_error     TEXT,
		mcp_server_id         TEXT NOT NULL,
		created_by            TEXT NOT NULL DEFAULT '',
		created_at            datetime,
		updated_at            datetime
	);`

const testEncryptionKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

func newTemplateAPITestHandler(t *testing.T) (*Handler, *gorm.DB) {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := gdb.Exec(templateAPITestDDL).Error; err != nil {
		t.Fatalf("ddl: %v", err)
	}
	enc, err := crypto.NewEncryptor(testEncryptionKey)
	if err != nil {
		t.Fatalf("encryptor: %v", err)
	}
	h := &Handler{
		templateRepo: repository.NewTemplateRepo(gdb),
		instanceRepo: repository.NewInstanceRepo(gdb, enc),
		repo:         repository.NewServerRepo(gdb, enc),
		config:       &config.Config{GoogleTemplatesRunnerAdminToken: "google-tok"},
	}
	return h, gdb
}

func seedTemplate(t *testing.T, gdb *gorm.DB, slug, runner string) {
	t.Helper()
	defaultEnv := `{}`
	if runner == RunnerNeo4j {
		defaultEnv = `{"NEO4J_READ_ONLY":"true"}`
	}
	// gdb.Create, not a raw INSERT: GORM binds json.RawMessage as a BLOB; a
	// SQL string literal is stored as TEXT, which the glebarez driver cannot
	// scan back into json.RawMessage (GetBySlug would then fail).
	if err := gdb.Create(&db.Template{
		Slug: slug, Name: slug, StdioCommand: "cmd-" + slug,
		StdioArgs: json.RawMessage(`[]`), DefaultEnv: json.RawMessage(defaultEnv),
		RequiredExtraEnv: json.RawMessage(`[]`), ToolPrefix: slug, Tags: json.RawMessage(`[]`),
		Kind: "stdio", Runner: runner, IsActive: true,
	}).Error; err != nil {
		t.Fatalf("seed template %s: %v", slug, err)
	}
}

func withNeo4jRunner(h *Handler, url string) {
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: runnerclient.New(url, "neo-tok"), URL: url, AdminToken: "neo-tok"}})
}

// fakeRunner answers every request with status/body.
func fakeRunner(t *testing.T, status int, body string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func multipartRequest(t *testing.T, target string, fields map[string]string) *http.Request {
	t.Helper()
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	for k, v := range fields {
		if err := mw.WriteField(k, v); err != nil {
			t.Fatalf("write field: %v", err)
		}
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("close multipart: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, target, &buf)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	return req
}
