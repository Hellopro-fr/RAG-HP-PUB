package gateway

import (
	"context"
	"testing"

	"mcp-gateway/internal/mcp"
)

func TestNewGateway(t *testing.T) {
	reg := NewRegistry()
	gw := New("test-gw", "1.0.0", reg)
	if gw == nil {
		t.Fatal("expected non-nil gateway")
	}
	if gw.name != "test-gw" {
		t.Errorf("expected name test-gw, got %s", gw.name)
	}
}

// fakeZohoCatalog satisfies the new ZohoUserCatalog interface.
type fakeZohoCatalog struct {
	stateByEmail map[string]ZohoCatalogState
}

func (f *fakeZohoCatalog) StateForEmail(_ context.Context, email string) ZohoCatalogState {
	return f.stateByEmail[email]
}

func TestFetchZohoStateForUser_ConfiguredAdmin(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-zoho", ToolPrefix: "zoho"})
	reg.Register(&BackendServer{ID: "srv-other"})

	gw := New("test", "0", reg)
	gw.SetZohoUserCatalog(&fakeZohoCatalog{
		stateByEmail: map[string]ZohoCatalogState{
			"admin@hp.fr": {
				Tools:      []mcp.Tool{{Name: "admin_tool"}},
				Configured: true,
			},
		},
	})

	got := gw.FetchZohoStateForUser(context.Background(), "admin@hp.fr")

	if len(got) != 1 {
		t.Fatalf("want 1 zoho backend entry, got %d", len(got))
	}
	state, ok := got["srv-zoho"]
	if !ok {
		t.Fatalf("missing srv-zoho entry: %+v", got)
	}
	if !state.Configured {
		t.Fatalf("want Configured=true")
	}
	if len(state.Tools) != 1 || state.Tools[0].Name != "admin_tool" {
		t.Fatalf("want admin_tool, got %+v", state.Tools)
	}
	if _, leak := got["srv-other"]; leak {
		t.Fatalf("non-zoho backend leaked into result")
	}
}

func TestFetchZohoStateForUser_NotConfigured(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-zoho", ToolPrefix: "zoho"})

	gw := New("test", "0", reg)
	gw.SetZohoUserCatalog(&fakeZohoCatalog{
		stateByEmail: map[string]ZohoCatalogState{
			"alice@hp.fr": {Configured: false},
		},
	})

	got := gw.FetchZohoStateForUser(context.Background(), "alice@hp.fr")

	state, ok := got["srv-zoho"]
	if !ok {
		t.Fatalf("zoho backend must appear even when unconfigured")
	}
	if state.Configured {
		t.Fatalf("want Configured=false")
	}
	if len(state.Tools) != 0 {
		t.Fatalf("unconfigured state must carry no tools, got %d", len(state.Tools))
	}
}

func TestFetchZohoStateForUser_EmptyEmail(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-zoho", ToolPrefix: "zoho"})
	gw := New("test", "0", reg)
	gw.SetZohoUserCatalog(&fakeZohoCatalog{})

	if got := gw.FetchZohoStateForUser(context.Background(), ""); got != nil {
		t.Fatalf("empty email must return nil, got %+v", got)
	}
}
