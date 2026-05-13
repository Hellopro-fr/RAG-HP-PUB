package authserver

import (
	"context"
	"reflect"
	"testing"

	"mcp-gateway/internal/mcp"
)

type stubZohoFetcher struct {
	result   map[string][]mcp.Tool
	gotEmail string
}

func (s *stubZohoFetcher) FetchZohoToolsForUser(_ context.Context, email string) map[string][]mcp.Tool {
	s.gotEmail = email
	return s.result
}

func TestApplyZohoUserTools_SubstitutesForKnownServer(t *testing.T) {
	servers := []authorizeServerDTO{
		{ID: "zoho-1", Name: "Zoho", Tools: []authorizeToolDTO{{Name: "admin_tool"}}},
		{ID: "other", Name: "Other", Tools: []authorizeToolDTO{{Name: "stay"}}},
	}
	zohoIDs := map[string]bool{"zoho-1": true}
	fetcher := &stubZohoFetcher{result: map[string][]mcp.Tool{
		"zoho-1": {{Name: "user_tool", Description: "user-specific"}},
	}}

	out := applyZohoUserTools(context.Background(), servers, zohoIDs, fetcher, "alice@hp.fr")

	if got, want := fetcher.gotEmail, "alice@hp.fr"; got != want {
		t.Fatalf("fetcher email got %q want %q", got, want)
	}
	wantZoho := []authorizeToolDTO{{Name: "user_tool", Description: "user-specific"}}
	if !reflect.DeepEqual(out[0].Tools, wantZoho) {
		t.Fatalf("zoho tools = %+v, want %+v", out[0].Tools, wantZoho)
	}
	if got := out[1].Tools[0].Name; got != "stay" {
		t.Fatalf("non-zoho tool changed: got %q", got)
	}
}

func TestApplyZohoUserTools_NoEmailKeepsAdmin(t *testing.T) {
	servers := []authorizeServerDTO{{ID: "zoho-1", Tools: []authorizeToolDTO{{Name: "admin_tool"}}}}
	fetcher := &stubZohoFetcher{result: map[string][]mcp.Tool{"zoho-1": {{Name: "user_tool"}}}}
	out := applyZohoUserTools(context.Background(), servers, map[string]bool{"zoho-1": true}, fetcher, "")
	if got := out[0].Tools[0].Name; got != "admin_tool" {
		t.Fatalf("expected admin_tool when email empty, got %q", got)
	}
}

func TestApplyZohoUserTools_NoFetcherKeepsAdmin(t *testing.T) {
	servers := []authorizeServerDTO{{ID: "zoho-1", Tools: []authorizeToolDTO{{Name: "admin_tool"}}}}
	out := applyZohoUserTools(context.Background(), servers, map[string]bool{"zoho-1": true}, nil, "alice@hp.fr")
	if got := out[0].Tools[0].Name; got != "admin_tool" {
		t.Fatalf("expected admin_tool when fetcher nil, got %q", got)
	}
}

func TestApplyZohoUserTools_EmptyLiveKeepsAdmin(t *testing.T) {
	servers := []authorizeServerDTO{{ID: "zoho-1", Tools: []authorizeToolDTO{{Name: "admin_tool"}}}}
	fetcher := &stubZohoFetcher{result: map[string][]mcp.Tool{}}
	out := applyZohoUserTools(context.Background(), servers, map[string]bool{"zoho-1": true}, fetcher, "alice@hp.fr")
	if got := out[0].Tools[0].Name; got != "admin_tool" {
		t.Fatalf("fail-open: expected admin_tool, got %q", got)
	}
}
