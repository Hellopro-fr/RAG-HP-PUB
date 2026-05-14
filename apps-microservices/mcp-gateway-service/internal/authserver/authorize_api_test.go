package authserver

import (
	"context"
	"testing"

	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
)

type fakeZohoState struct {
	stateByEmail map[string]map[string]gateway.ZohoServerState
}

func (f *fakeZohoState) FetchZohoStateForUser(_ context.Context, email string) map[string]gateway.ZohoServerState {
	return f.stateByEmail[email]
}

func TestApplyZohoUserState_ConfiguredServerKeepsTools(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-zoho",
		Name:  "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"alice@hp.fr": {"srv-zoho": {
			Tools:      []mcp.Tool{{Name: "alice_tool"}},
			Configured: true,
		}},
	}}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "alice@hp.fr", "https://docs/zohocrm")

	if len(out) != 1 {
		t.Fatalf("want 1 entry, got %d", len(out))
	}
	if !out[0].Configured {
		t.Fatalf("Configured must be true on the in-place server")
	}
	if out[0].DocsURL != "" {
		t.Fatalf("DocsURL must be empty when Configured=true, got %q", out[0].DocsURL)
	}
	if len(out[0].Tools) != 1 || out[0].Tools[0].Name != "alice_tool" {
		t.Fatalf("want alice_tool, got %+v", out[0].Tools)
	}
}

func TestApplyZohoUserState_UnconfiguredServerGetsDocsURL(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-zoho",
		Name:  "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"bob@hp.fr": {"srv-zoho": {Configured: false}},
	}}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "bob@hp.fr", "https://docs/zohocrm")

	if out[0].Configured {
		t.Fatalf("Configured must be false")
	}
	if out[0].DocsURL != "https://docs/zohocrm" {
		t.Fatalf("DocsURL must be the supplied value, got %q", out[0].DocsURL)
	}
	if len(out[0].Tools) != 0 {
		t.Fatalf("unconfigured server must carry no tools, got %+v", out[0].Tools)
	}
}

func TestApplyZohoUserState_NonZohoUntouched(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-other",
		Name:  "Other",
		Tools: []authorizeToolDTO{{Name: "x"}},
	}}
	zohoIDs := map[string]bool{} // none
	fetcher := &fakeZohoState{}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "alice@hp.fr", "https://docs/zohocrm")

	if out[0].Configured {
		t.Fatalf("non-Zoho server must not get Configured flag set")
	}
	if out[0].DocsURL != "" {
		t.Fatalf("non-Zoho server must not get DocsURL set")
	}
	if len(out[0].Tools) != 1 {
		t.Fatalf("non-Zoho server tools must be untouched")
	}
}

func TestApplyZohoUserState_NilFetcherLeavesInputAlone(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-zoho",
		Name:  "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}

	out := applyZohoUserState(context.Background(), in, zohoIDs, nil, "alice@hp.fr", "https://docs/zohocrm")

	if out[0].Configured || out[0].DocsURL != "" {
		t.Fatalf("nil fetcher must leave Configured/DocsURL unset, got %+v", out[0])
	}
	if len(out[0].Tools) != 1 {
		t.Fatalf("nil fetcher must leave tools intact")
	}
}

func TestApplyZohoUserState_MissingStateEntryTreatedAsUnconfigured(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-zoho",
		Name:  "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}
	// Fetcher returns a non-empty state map but with no entry for srv-zoho.
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"alice@hp.fr": {"srv-other-zoho": {Configured: true}},
	}}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "alice@hp.fr", "https://docs/zohocrm")

	if out[0].Configured {
		t.Fatalf("missing state entry must be treated as unconfigured")
	}
	if out[0].DocsURL != "https://docs/zohocrm" {
		t.Fatalf("missing state entry must surface docs URL")
	}
	if len(out[0].Tools) != 0 {
		t.Fatalf("missing state entry must clear tools, got %+v", out[0].Tools)
	}
}
