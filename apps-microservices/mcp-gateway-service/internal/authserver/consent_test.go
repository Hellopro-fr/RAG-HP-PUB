package authserver

import (
	"testing"

	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
)

func TestGenerateCSRFToken(t *testing.T) {
	token, err := generateCSRFToken()
	if err != nil {
		t.Fatalf("generateCSRFToken: %v", err)
	}
	if len(token) < 32 {
		t.Fatal("CSRF token too short")
	}
}

func TestPartitionZohoServerDecision_NotZoho(t *testing.T) {
	zohoIDs := map[string]bool{"srv-zoho": true}
	state := map[string]gateway.ZohoServerState{}

	unconf, tools := decideZohoServerEntry("srv-other", zohoIDs, state)
	if unconf {
		t.Fatalf("non-Zoho server must not be marked unconfigured")
	}
	if tools != nil {
		t.Fatalf("non-Zoho server must return nil tools (callers use srv.Tools)")
	}
}

func TestPartitionZohoServerDecision_ZohoConfigured(t *testing.T) {
	zohoIDs := map[string]bool{"srv-zoho": true}
	state := map[string]gateway.ZohoServerState{
		"srv-zoho": {Tools: []mcp.Tool{{Name: "alice_tool"}}, Configured: true},
	}

	unconf, tools := decideZohoServerEntry("srv-zoho", zohoIDs, state)
	if unconf {
		t.Fatalf("configured Zoho must NOT be unconfigured")
	}
	if len(tools) != 1 || tools[0].Name != "alice_tool" {
		t.Fatalf("configured Zoho must return state tools, got %+v", tools)
	}
}

func TestPartitionZohoServerDecision_ZohoUnconfiguredExplicit(t *testing.T) {
	zohoIDs := map[string]bool{"srv-zoho": true}
	state := map[string]gateway.ZohoServerState{
		"srv-zoho": {Configured: false},
	}

	unconf, tools := decideZohoServerEntry("srv-zoho", zohoIDs, state)
	if !unconf {
		t.Fatalf("explicitly unconfigured Zoho must be unconfigured")
	}
	if tools != nil {
		t.Fatalf("unconfigured Zoho must return nil tools")
	}
}

func TestPartitionZohoServerDecision_ZohoMissingFromState(t *testing.T) {
	zohoIDs := map[string]bool{"srv-zoho": true}
	state := map[string]gateway.ZohoServerState{} // no entry

	unconf, tools := decideZohoServerEntry("srv-zoho", zohoIDs, state)
	if !unconf {
		t.Fatalf("missing-state Zoho must be treated as unconfigured")
	}
	if tools != nil {
		t.Fatalf("missing-state Zoho must return nil tools")
	}
}

func TestPartitionZohoServerDecision_NilState(t *testing.T) {
	zohoIDs := map[string]bool{"srv-zoho": true}

	unconf, tools := decideZohoServerEntry("srv-zoho", zohoIDs, nil)
	if !unconf {
		t.Fatalf("nil state on a Zoho server must be treated as unconfigured")
	}
	if tools != nil {
		t.Fatalf("nil state must return nil tools")
	}
}

func TestConsentScopeJSON(t *testing.T) {
	scope := ConsentScope{
		ServerIDs: []string{"srv-1", "srv-2"},
	}
	j := scope.ToJSON()
	if j == "" {
		t.Fatal("expected non-empty JSON")
	}
	parsed, err := ParseConsentScope(j)
	if err != nil {
		t.Fatalf("ParseConsentScope: %v", err)
	}
	if len(parsed.ServerIDs) != 2 {
		t.Fatalf("expected 2 server IDs, got %d", len(parsed.ServerIDs))
	}
}
