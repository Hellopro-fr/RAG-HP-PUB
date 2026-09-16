package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
)

// Regression coverage for the three additional min_role-drop sites found
// during Task 3's controller review: handleCreateServer, handleEnableServer
// (disable→enable cycle) and handleDiscoverServer. Each registers a fresh
// *gateway.BackendServer built from an upstream `initialize` result that
// knows nothing about min_role — without the SetMinRole push added to each
// handler, the gated server ends up in the registry with MinRole == "".
//
// newMinRoleTestDB mirrors the narrow hand-rolled-DDL pattern used across
// this package's repo tests (AutoMigrate on the real GORM models isn't
// portable to SQLite because of the MySQL-only `datetime(3)` column type).
// The DDL below covers every column ServerRepo.Create/GetByID touches, plus
// empty server_tools/server_resources/server_prompts/prompt_arguments/
// server_tags tables so GetByID's Preload calls don't fail on a missing
// table.
func newMinRoleTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Silent),
	})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE mcp_servers (
			id                   TEXT PRIMARY KEY,
			name                 TEXT NOT NULL DEFAULT '',
			url                  TEXT NOT NULL DEFAULT '',
			message_url          TEXT,
			transport_type       TEXT,
			server_name          TEXT,
			server_version       TEXT,
			auth_headers         BLOB,
			transport_preference TEXT NOT NULL DEFAULT 'auto',
			connect_timeout_ms   INTEGER NOT NULL DEFAULT 10000,
			capabilities_raw     TEXT,
			mcp_transport        TEXT NOT NULL DEFAULT 'http',
			mcp_command          TEXT,
			mcp_args             TEXT,
			mcp_env              TEXT,
			tool_prefix          TEXT NOT NULL DEFAULT '',
			icon                 TEXT NOT NULL DEFAULT '',
			min_role             TEXT NOT NULL DEFAULT '',
			template_slug        TEXT NOT NULL DEFAULT '',
			doc_slug             TEXT,
			doc_description      TEXT,
			doc_config_guide     TEXT,
			is_active            INTEGER NOT NULL DEFAULT 1,
			health_status        TEXT NOT NULL DEFAULT 'unknown',
			last_health_check    datetime,
			last_error           TEXT,
			last_discovered_at   datetime,
			created_by           TEXT NOT NULL DEFAULT '',
			created_at           datetime,
			updated_at           datetime
		);
		CREATE TABLE server_tools (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			server_id     TEXT NOT NULL,
			name          TEXT NOT NULL,
			description   TEXT,
			input_schema  TEXT NOT NULL DEFAULT '{}',
			is_active     INTEGER NOT NULL DEFAULT 1
		);
		CREATE TABLE server_resources (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			server_id     TEXT NOT NULL,
			uri           TEXT NOT NULL,
			name          TEXT NOT NULL,
			description   TEXT,
			mime_type     TEXT
		);
		CREATE TABLE server_prompts (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			server_id     TEXT NOT NULL,
			name          TEXT NOT NULL,
			description   TEXT
		);
		CREATE TABLE prompt_arguments (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			prompt_id     INTEGER NOT NULL,
			name          TEXT NOT NULL,
			description   TEXT,
			is_required   INTEGER NOT NULL DEFAULT 0
		);
		CREATE TABLE server_tags (
			server_id TEXT NOT NULL,
			tag       TEXT NOT NULL,
			PRIMARY KEY (server_id, tag)
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create tables: %v", err)
	}
	return gdb
}

// newMinRoleHandler wires a Handler with a real (sqlite-backed) ServerRepo,
// a real Registry and a real Gateway. allowInternalURLs is forced to true
// so the httptest.Server loopback URL passes SSRF validation.
func newMinRoleHandler(t *testing.T) *Handler {
	t.Helper()
	gdb := newMinRoleTestDB(t)
	repo := repository.NewServerRepo(gdb, nil)
	registry := gateway.NewRegistry()
	gw := gateway.New("test-gateway", "0.0.1", registry)
	return NewHandler(repo, gw, registry, true, nil, nil, nil, nil)
}

// fakeMCPBackend answers the minimal subset of the MCP handshake that
// gateway.DiscoverAndRegister needs: a single POST /mcp endpoint that always
// responds to "initialize" with a capabilities-free InitializeResult (so the
// gateway never follows up with tools/list, resources/list or prompts/list).
func fakeMCPBackend(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/mcp", func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var req mcp.Request
		_ = json.Unmarshal(body, &req)

		result := mcp.InitializeResult{
			ProtocolVersion: mcp.ProtocolVersion,
			ServerInfo:      mcp.Implementation{Name: "fake-backend", Version: "1.0"},
		}
		resultRaw, _ := json.Marshal(result)
		resp := mcp.Response{JSONRPC: "2.0", ID: json.RawMessage(`1`), Result: resultRaw}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	})
	return httptest.NewServer(mux)
}

// TestHandleCreateServer_AutoDiscover_PushesMinRoleToRegistry is the worst of
// the three regressions: this is a brand-new id, so gateway.go's rediscovery
// preservation clause has no prev entry to fall back to. Without an explicit
// SetMinRole push in handleCreateServer's auto-discover success branch, a
// server created with min_role="admin" registers in memory as MinRole=""
// — public — and the gate never closes at all until process restart.
func TestHandleCreateServer_AutoDiscover_PushesMinRoleToRegistry(t *testing.T) {
	backend := fakeMCPBackend(t)
	defer backend.Close()

	h := newMinRoleHandler(t)

	reqBody, _ := json.Marshal(CreateServerRequest{
		Name:         "gated-server",
		URL:          backend.URL,
		AutoDiscover: true,
		MinRole:      "admin",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/servers", bytes.NewReader(reqBody))
	rec := httptest.NewRecorder()

	h.handleCreateServer(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("POST /servers status = %d, want 201, body=%s", rec.Code, rec.Body.String())
	}
	var created ServerResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	backendEntry := h.registry.FindByID(created.ID)
	if backendEntry == nil {
		t.Fatalf("server %s was not registered", created.ID)
	}
	if backendEntry.MinRole != "admin" {
		t.Fatalf("registry MinRole = %q after create, want %q — the gate never closed", backendEntry.MinRole, "admin")
	}
}

// TestHandleEnableServer_DisableEnableCycle_PreservesMinRole guards the
// second regression: handleDisableServer unregisters the backend outright,
// so gateway.go's preservation clause has no prev entry when
// handleEnableServer re-discovers it. Without an explicit SetMinRole push in
// handleEnableServer's success branch, a disable→enable cycle drops
// min_role.
func TestHandleEnableServer_DisableEnableCycle_PreservesMinRole(t *testing.T) {
	backend := fakeMCPBackend(t)
	defer backend.Close()

	h := newMinRoleHandler(t)

	reqBody, _ := json.Marshal(CreateServerRequest{
		Name:         "gated-server",
		URL:          backend.URL,
		AutoDiscover: true,
		MinRole:      "admin",
	})
	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/servers", bytes.NewReader(reqBody))
	createRec := httptest.NewRecorder()
	h.handleCreateServer(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("setup create status = %d, body=%s", createRec.Code, createRec.Body.String())
	}
	var created ServerResponse
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	id := created.ID

	if got := h.registry.FindByID(id); got == nil || got.MinRole != "admin" {
		t.Fatalf("setup: MinRole not admin right after create (got %+v)", got)
	}

	// Disable: unregisters the backend from the in-memory registry.
	disableReq := httptest.NewRequest(http.MethodPost, "/api/v1/servers/"+id+"/disable", nil)
	disableRec := httptest.NewRecorder()
	h.handleDisableServer(disableRec, disableReq)
	if disableRec.Code != http.StatusOK {
		t.Fatalf("disable status = %d, body=%s", disableRec.Code, disableRec.Body.String())
	}
	if h.registry.FindByID(id) != nil {
		t.Fatalf("expected backend to be unregistered after disable")
	}

	// Enable: re-discovers and re-registers the backend from scratch.
	enableReq := httptest.NewRequest(http.MethodPost, "/api/v1/servers/"+id+"/enable", nil)
	enableRec := httptest.NewRecorder()
	h.handleEnableServer(enableRec, enableReq)
	if enableRec.Code != http.StatusOK {
		t.Fatalf("enable status = %d, body=%s", enableRec.Code, enableRec.Body.String())
	}

	backendEntry := h.registry.FindByID(id)
	if backendEntry == nil {
		t.Fatalf("server %s was not registered after enable", id)
	}
	if backendEntry.MinRole != "admin" {
		t.Fatalf("registry MinRole = %q after disable→enable cycle, want %q", backendEntry.MinRole, "admin")
	}
}

// TestHandleDiscoverServer_PreservesMinRole guards the third regression:
// handleDiscoverServer explicitly Unregisters the backend before
// re-discovering it, same as the disable path, so an admin clicking
// "Rediscover" on a gated server would silently make it public without the
// SetMinRole push.
func TestHandleDiscoverServer_PreservesMinRole(t *testing.T) {
	backend := fakeMCPBackend(t)
	defer backend.Close()

	h := newMinRoleHandler(t)

	reqBody, _ := json.Marshal(CreateServerRequest{
		Name:         "gated-server",
		URL:          backend.URL,
		AutoDiscover: true,
		MinRole:      "admin",
	})
	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/servers", bytes.NewReader(reqBody))
	createRec := httptest.NewRecorder()
	h.handleCreateServer(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("setup create status = %d, body=%s", createRec.Code, createRec.Body.String())
	}
	var created ServerResponse
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	id := created.ID

	discoverReq := httptest.NewRequest(http.MethodPost, "/api/v1/servers/"+id+"/discover", nil)
	discoverRec := httptest.NewRecorder()
	h.handleDiscoverServer(discoverRec, discoverReq)
	if discoverRec.Code != http.StatusOK {
		t.Fatalf("discover status = %d, body=%s", discoverRec.Code, discoverRec.Body.String())
	}

	backendEntry := h.registry.FindByID(id)
	if backendEntry == nil {
		t.Fatalf("server %s was not registered after re-discover", id)
	}
	if backendEntry.MinRole != "admin" {
		t.Fatalf("registry MinRole = %q after explicit re-discover, want %q — an admin clicking \"Rediscover\" would have made this server public", backendEntry.MinRole, "admin")
	}
}
