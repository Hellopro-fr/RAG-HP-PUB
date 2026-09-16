package app

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/health"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
)

// TestLoadServersFromDB_PreservesMinRole guards the sixth (and most severe)
// min_role registry-drop regression: loadServersFromDB runs at boot, before
// the registry has any entries, so gateway.go's prev-preservation clause has
// nothing to preserve from. The success branch re-pushed ToolPrefix, Tags
// and tool active states but not MinRole — meaning every gated server whose
// backend was reachable at boot came up in the registry as MinRole == "",
// i.e. public, on every gateway restart. Registers one gated ("admin") and
// one public ("") server, both discoverable, and asserts only the gated one
// keeps its MinRole after loadServersFromDB runs (public server is a
// control against an over-broad fix).
//
// The DDL below mirrors the hand-rolled-DDL pattern already used across this
// package's sibling tests (internal/api/min_role_registration_regression_test.go)
// — AutoMigrate on the real GORM models isn't sqlite-portable because of the
// MySQL-only `datetime(3)` column type.
func newLoadServersTestDB(t *testing.T) *gorm.DB {
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

// fakeMCPBackendForBoot answers the minimal MCP handshake DiscoverAndRegister
// needs, same shape as the api package's fakeMCPBackend helper.
func fakeMCPBackendForBoot(t *testing.T) *httptest.Server {
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

func TestLoadServersFromDB_PreservesMinRole(t *testing.T) {
	gatedBackend := fakeMCPBackendForBoot(t)
	defer gatedBackend.Close()
	publicBackend := fakeMCPBackendForBoot(t)
	defer publicBackend.Close()

	gdb := newLoadServersTestDB(t)
	repo := repository.NewServerRepo(gdb, nil)

	gatedID := "gated-srv-1"
	publicID := "public-srv-1"
	if err := gdb.Create(&db.MCPServer{
		ID: gatedID, Name: "gated-server", URL: gatedBackend.URL,
		IsActive: true, MinRole: "admin",
	}).Error; err != nil {
		t.Fatalf("seed gated server: %v", err)
	}
	if err := gdb.Create(&db.MCPServer{
		ID: publicID, Name: "public-server", URL: publicBackend.URL,
		IsActive: true,
	}).Error; err != nil {
		t.Fatalf("seed public server: %v", err)
	}

	registry := gateway.NewRegistry()
	gw := gateway.New("test-gateway", "0.0.1", registry)
	checker := health.NewChecker(repo, gw, registry, 0, nil)

	loadServersFromDB(gw, registry, repo, checker)

	gatedEntry := registry.FindByID(gatedID)
	if gatedEntry == nil {
		t.Fatalf("gated server %s was not registered at boot", gatedID)
	}
	if gatedEntry.MinRole != "admin" {
		t.Fatalf("registry MinRole = %q after boot load, want %q — every gated server whose backend was reachable would come up public on every restart", gatedEntry.MinRole, "admin")
	}

	publicEntry := registry.FindByID(publicID)
	if publicEntry == nil {
		t.Fatalf("public server %s was not registered at boot", publicID)
	}
	if publicEntry.MinRole != "" {
		t.Fatalf("registry MinRole = %q for the public control server after boot load, want empty", publicEntry.MinRole)
	}
}
