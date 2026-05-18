package gateway

import (
	"testing"

	"mcp-gateway/internal/mcp"
)

// TestZohoCatalogState_ZeroValue verifies the zero value of ZohoCatalogState
// is valid and that the type can be composed as expected.
func TestZohoCatalogState_ZeroValue(t *testing.T) {
	var s ZohoCatalogState
	if s.Configured {
		t.Error("zero-value ZohoCatalogState.Configured must be false")
	}
	if s.Tools != nil {
		t.Error("zero-value ZohoCatalogState.Tools must be nil")
	}
}

// TestZohoCatalogState_Populated verifies fields are stored and retrieved correctly.
func TestZohoCatalogState_Populated(t *testing.T) {
	tools := []mcp.Tool{
		{Name: "get_records", Description: "Fetch Zoho CRM records"},
	}
	s := ZohoCatalogState{
		Tools:      tools,
		Configured: true,
	}
	if !s.Configured {
		t.Error("expected Configured to be true")
	}
	if len(s.Tools) != 1 {
		t.Errorf("expected 1 tool, got %d", len(s.Tools))
	}
	if s.Tools[0].Name != "get_records" {
		t.Errorf("unexpected tool name: %s", s.Tools[0].Name)
	}
}

// TestZohoServerState_ZeroValue verifies the zero value of ZohoServerState.
func TestZohoServerState_ZeroValue(t *testing.T) {
	var s ZohoServerState
	if s.Configured {
		t.Error("zero-value ZohoServerState.Configured must be false")
	}
	if s.Tools != nil {
		t.Error("zero-value ZohoServerState.Tools must be nil")
	}
}

// TestZohoServerState_Populated verifies ZohoServerState stores fields correctly.
func TestZohoServerState_Populated(t *testing.T) {
	tools := []mcp.Tool{
		{Name: "search_leads", Description: "Search Zoho CRM leads"},
	}
	s := ZohoServerState{
		Tools:      tools,
		Configured: true,
	}
	if !s.Configured {
		t.Error("expected Configured to be true")
	}
	if len(s.Tools) != 1 {
		t.Errorf("expected 1 tool, got %d", len(s.Tools))
	}
}
