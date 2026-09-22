package health

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
)

// fakeMCPBackend answers the minimal subset of the MCP handshake that
// gateway.DiscoverAndRegister needs: a single POST /mcp endpoint that always
// responds to "initialize" with a capabilities-free InitializeResult, so the
// gateway never follows up with tools/list, resources/list or prompts/list.
// Mirrors internal/api/min_role_registration_regression_test.go's helper of
// the same name — duplicated here because Go test helpers aren't exported
// across packages.
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

// newHealthTestChecker wires a Checker with a real (sqlite-backed, tableless)
// ServerRepo, a real Registry and a real Gateway. UpdateHealth's UPDATE
// statement will fail against the missing mcp_servers table, but checkOne
// discards that error (`_ = c.repo.UpdateHealth(...)`), so a real *gorm.DB is
// enough to avoid the nil-pointer panic without needing any DDL.
func newHealthTestChecker(t *testing.T) (*Checker, *gateway.Registry) {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Silent),
	})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	repo := repository.NewServerRepo(gdb, nil)
	registry := gateway.NewRegistry()
	gw := gateway.New("test-gateway", "0.0.1", registry)
	c := NewChecker(repo, gw, registry, 30*time.Second, nil)
	return c, registry
}

// TestCheckOne_PushesMinRoleWhenRegistryEntryMissing guards the Critical
// finding: a gated server that reaches the health checker with NO prior
// registry entry (e.g. handleCreateServer's SetMinRole sits inside the
// AutoDiscover branch, so a gated server created with auto-discover
// unchecked never gets one) must still end up gated after the health
// checker's re-discovery, because gateway.go's `prev`-preservation clause
// has nothing to preserve from when the registry entry doesn't exist yet.
//
// Includes a public control server to prove the fix doesn't spuriously gate
// an ungated backend.
func TestCheckOne_PushesMinRoleWhenRegistryEntryMissing(t *testing.T) {
	gatedBackend := fakeMCPBackend(t)
	defer gatedBackend.Close()
	publicBackend := fakeMCPBackend(t)
	defer publicBackend.Close()

	c, registry := newHealthTestChecker(t)

	gatedSrv := &db.MCPServer{ID: "gated-1", URL: gatedBackend.URL, MinRole: "admin", HealthStatus: "unknown"}
	publicSrv := &db.MCPServer{ID: "public-1", URL: publicBackend.URL, MinRole: "", HealthStatus: "unknown"}

	// Precondition: neither server has a registry entry yet — this is the
	// exact hole from Finding 1 (no prior entry for checkOne's DiscoverAndRegister
	// to preserve MinRole from).
	if registry.FindByID("gated-1") != nil || registry.FindByID("public-1") != nil {
		t.Fatalf("setup: registry should start empty for this test")
	}

	c.checkOne(gatedSrv, nil)
	c.checkOne(publicSrv, nil)

	gatedEntry := registry.FindByID("gated-1")
	if gatedEntry == nil {
		t.Fatalf("gated server was not registered by checkOne")
	}
	if gatedEntry.MinRole != "admin" {
		t.Fatalf("registry MinRole = %q after checkOne with no prior registry entry, want %q — the health checker registered a gated server as public", gatedEntry.MinRole, "admin")
	}

	publicEntry := registry.FindByID("public-1")
	if publicEntry == nil {
		t.Fatalf("public control server was not registered by checkOne")
	}
	if publicEntry.MinRole != "" {
		t.Fatalf("registry MinRole = %q for the public control server after checkOne, want empty", publicEntry.MinRole)
	}
}
