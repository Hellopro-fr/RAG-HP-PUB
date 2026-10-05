package api

import (
	"context"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"testing"
	"time"

	gosqlite "github.com/glebarez/go-sqlite"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
)

// ServerRepo.SaveDiscoveredCapabilities stamps last_discovered_at with the
// MySQL NOW(3); SQLite has no NOW, so the test binary provides one. It must
// be registered before any connection is opened, hence init.
func init() {
	gosqlite.MustRegisterScalarFunction("NOW", -1, func(*gosqlite.FunctionContext, []driver.Value) (driver.Value, error) {
		return time.Now().UTC().Format("2006-01-02 15:04:05.000"), nil
	})
}

// hdSixTools stands in for the six tools mcp-hellodata-service lists to an
// authorized caller.
func hdSixTools() []mcp.Tool {
	names := []string{"compter", "echantillon", "export_csv", "recup_acheteur", "bilan_campagnes", "enregistrer_reponses"}
	out := make([]mcp.Tool, 0, len(names))
	for _, n := range names {
		out = append(out, mcp.Tool{Name: n, Description: n, InputSchema: json.RawMessage(`{"type":"object"}`)})
	}
	return out
}

func asUser(email, role string) context.Context {
	ctx := context.WithValue(context.Background(), auth.ContextKeyUserEmail, email)
	return context.WithValue(ctx, auth.ContextKeyUserRole, role)
}

// newHellodataCatalogHandler creates one server row with the given prefix and
// stored tools, and returns a Handler using the given lister.
func newHellodataCatalogHandler(t *testing.T, prefix string, stored []string, lister hellodataToolLister) *Handler {
	t.Helper()
	h := newMinRoleHandler(t)
	srv := &db.MCPServer{ID: "hd-1", Name: "hellodata", URL: "http://mcp-hellodata-service:8597/mcp", ToolPrefix: prefix, IsActive: true}
	if err := h.repo.Create(srv); err != nil {
		t.Fatalf("create server: %v", err)
	}
	if len(stored) > 0 {
		seed := &db.MCPServer{ID: "hd-1"}
		for _, n := range stored {
			seed.Tools = append(seed.Tools, db.ServerTool{Name: n, InputSchema: json.RawMessage(`{}`)})
		}
		if _, err := h.repo.SaveDiscoveredCapabilities(seed); err != nil {
			t.Fatalf("seed tools: %v", err)
		}
	}
	h.hellodataLister = lister
	return h
}

func storedToolNames(t *testing.T, h *Handler) []string {
	t.Helper()
	srv, err := h.repo.GetByID("hd-1")
	if err != nil {
		t.Fatalf("get server: %v", err)
	}
	out := make([]string, 0, len(srv.Tools))
	for _, tl := range srv.Tools {
		out = append(out, tl.Name)
	}
	return out
}

// anonymousBackend is what DiscoverAndRegister produces for hellodata: the
// wrapper answered the anonymous tools/list with an empty list.
func anonymousBackend(prefix string) *gateway.BackendServer {
	return &gateway.BackendServer{
		ID:          "hd-1",
		MessageURL:  "http://mcp-hellodata-service:8597/mcp",
		ToolPrefix:  prefix,
		AuthHeaders: map[string]string{"X-Backend-Key": "k"},
	}
}

func TestSaveBackendCapabilities_HellodataAdminPersistsLiveCatalog(t *testing.T) {
	var got map[string]string
	h := newHellodataCatalogHandler(t, "hellodata", nil, func(_ context.Context, _ string, headers map[string]string) ([]mcp.Tool, error) {
		got = headers
		return hdSixTools(), nil
	})

	h.saveBackendCapabilities(asUser("admin@example.test", auth.RoleAdmin), "hd-1", anonymousBackend("hellodata"))

	if n := len(storedToolNames(t, h)); n != 6 {
		t.Fatalf("stored tools = %d, want 6", n)
	}
	if got[gateway.EndUserEmailHeader] != "admin@example.test" || got[gateway.EndUserRoleHeader] != auth.RoleAdmin {
		t.Fatalf("identity headers not sent: %v", got)
	}
	if got["X-Backend-Key"] != "k" {
		t.Fatalf("backend auth headers dropped: %v", got)
	}
	if _, ok := got[gateway.EndUserGrantedHeader]; ok {
		t.Fatalf("X-End-User-Granted must not be sent on admin discovery: %v", got)
	}
}

func TestSaveBackendCapabilities_HellodataNonAdminKeepsStoredTools(t *testing.T) {
	called := false
	h := newHellodataCatalogHandler(t, "hellodata", []string{"compter", "export_csv"}, func(context.Context, string, map[string]string) ([]mcp.Tool, error) {
		called = true
		return hdSixTools(), nil
	})

	for _, ctx := range []context.Context{asUser("viewer@example.test", auth.RoleConfigOnly), context.Background()} {
		h.saveBackendCapabilities(ctx, "hd-1", anonymousBackend("hellodata"))
		if n := len(storedToolNames(t, h)); n != 2 {
			t.Fatalf("stored tools = %d, want the 2 already stored", n)
		}
	}
	if called {
		t.Fatal("a non-admin caller must not trigger the identity fetch")
	}
}

func TestSaveBackendCapabilities_HellodataFetchFailureKeepsStoredTools(t *testing.T) {
	for name, lister := range map[string]hellodataToolLister{
		"error": func(context.Context, string, map[string]string) ([]mcp.Tool, error) { return nil, errors.New("down") },
		"empty": func(context.Context, string, map[string]string) ([]mcp.Tool, error) { return nil, nil },
	} {
		t.Run(name, func(t *testing.T) {
			h := newHellodataCatalogHandler(t, "hellodata", []string{"compter"}, lister)
			h.saveBackendCapabilities(asUser("admin@example.test", auth.RoleAdmin), "hd-1", anonymousBackend("hellodata"))
			if n := len(storedToolNames(t, h)); n != 1 {
				t.Fatalf("stored tools = %d, want the 1 already stored", n)
			}
		})
	}
}

// The bulk rediscover path does not push ToolPrefix back into the registry:
// the DB row must still identify the backend as hellodata.
func TestSaveBackendCapabilities_HellodataPrefixFromDBRow(t *testing.T) {
	h := newHellodataCatalogHandler(t, "hellodata", nil, func(context.Context, string, map[string]string) ([]mcp.Tool, error) {
		return hdSixTools(), nil
	})
	h.saveBackendCapabilities(asUser("admin@example.test", auth.RoleAdmin), "hd-1", anonymousBackend(""))
	if n := len(storedToolNames(t, h)); n != 6 {
		t.Fatalf("stored tools = %d, want 6", n)
	}
}

func TestSaveBackendCapabilities_OtherServerUnchanged(t *testing.T) {
	called := false
	h := newHellodataCatalogHandler(t, "leexi", []string{"old"}, func(context.Context, string, map[string]string) ([]mcp.Tool, error) {
		called = true
		return hdSixTools(), nil
	})
	backend := anonymousBackend("leexi")
	backend.Tools = []mcp.Tool{{Name: "search_calls", InputSchema: json.RawMessage(`{}`)}}

	h.saveBackendCapabilities(asUser("admin@example.test", auth.RoleAdmin), "hd-1", backend)

	names := storedToolNames(t, h)
	if called || len(names) != 1 || names[0] != "search_calls" {
		t.Fatalf("non-hellodata server: called=%t names=%v, want discovered tools only", called, names)
	}
}
