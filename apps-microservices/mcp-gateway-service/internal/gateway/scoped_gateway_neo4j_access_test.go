package gateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/mcp"
)

// neo4jGateFixture is a scoped gateway over two backends sharing one stub
// MCP upstream: "srv-neo4j" (a Neo4j template instance whose registry entry
// has an EMPTY TemplateSlug, exactly like a backend discovered at boot) and
// "srv-plain" (a regular server). hits counts every request that reached the
// upstream.
type neo4jGateFixture struct {
	gw     *Gateway
	sg     *ScopedGateway
	grants *countingGrants
	hits   *int32
}

func newNeo4jGateFixture(t *testing.T, wireGate bool) *neo4jGateFixture {
	t.Helper()
	var hits int32
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{}}`))
	}))
	t.Cleanup(upstream.Close)

	reg := NewRegistry()
	reg.Register(&BackendServer{
		ID:         "srv-neo4j",
		MessageURL: upstream.URL,
		ToolPrefix: "neo4jprod",
		Tools:      []mcp.Tool{{Name: "read_neo4j_cypher", IsActive: true}},
		Resources:  []mcp.Resource{{URI: "neo4j://schema", Name: "schema"}},
		Prompts:    []mcp.Prompt{{Name: "neo4j_prompt"}},
	})
	reg.Register(&BackendServer{
		ID:         "srv-plain",
		MessageURL: upstream.URL,
		Tools:      []mcp.Tool{{Name: "echo", IsActive: true}},
		Resources:  []mcp.Resource{{URI: "plain://doc", Name: "doc"}},
		Prompts:    []mcp.Prompt{{Name: "plain_prompt"}},
	})
	gw := New("gw", "1.0", reg)
	grants := &countingGrants{grants: map[string]map[string]bool{
		"srv-neo4j": {"alice@hp.fr": true},
	}}
	if wireGate {
		gw.SetNeo4jAccess(NewNeo4jAccess(
			&countingTemplates{rows: map[string]*db.Template{"neo4j": {Slug: "neo4j", Runner: "neo4j"}}},
			&countingServerSlugs{slugs: map[string]string{"srv-neo4j": "neo4j"}},
			&countingUsers{rows: map[string]*db.GatewayUser{"admin@hp.fr": {Email: "admin@hp.fr", Role: auth.RoleAdmin, IsAllowed: true}}},
			grants,
		))
	}
	sg := NewScopedGateway(gw, map[string]bool{"srv-neo4j": true, "srv-plain": true}, nil, nil)
	return &neo4jGateFixture{gw: gw, sg: sg, grants: grants, hits: &hits}
}

func (f *neo4jGateFixture) call(t *testing.T, ctx context.Context, method string, params any) *mcp.Response {
	t.Helper()
	req := &mcp.Request{JSONRPC: "2.0", ID: json.RawMessage(`1`), Method: method}
	if params != nil {
		raw, err := json.Marshal(params)
		if err != nil {
			t.Fatalf("marshal params: %v", err)
		}
		req.Params = raw
	}
	return f.sg.Handle(ctx, req)
}

// listedNames returns the names (tools, prompts) or URIs (resources) of a
// list response.
func listedNames(t *testing.T, resp *mcp.Response) map[string]bool {
	t.Helper()
	if resp == nil || resp.Error != nil {
		t.Fatalf("unexpected error response: %+v", resp)
	}
	var out struct {
		Tools     []mcp.Tool     `json:"tools"`
		Resources []mcp.Resource `json:"resources"`
		Prompts   []mcp.Prompt   `json:"prompts"`
	}
	if err := json.Unmarshal(resp.Result, &out); err != nil {
		t.Fatalf("unmarshal list result: %v", err)
	}
	names := make(map[string]bool)
	for _, x := range out.Tools {
		names[x.Name] = true
	}
	for _, x := range out.Resources {
		names[x.URI] = true
	}
	for _, x := range out.Prompts {
		names[x.Name] = true
	}
	return names
}

var neo4jGateListCases = []struct {
	method     string
	restricted string
	plain      string
}{
	{"tools/list", "neo4jprod_read_neo4j_cypher", "echo"},
	{"resources/list", "neo4j://schema", "plain://doc"},
	{"prompts/list", "neo4j_prompt", "plain_prompt"},
}

var neo4jGateCallCases = []struct {
	method     string
	restricted any
	plain      any
}{
	{"tools/call", mcp.CallToolParams{Name: "neo4jprod_read_neo4j_cypher"}, mcp.CallToolParams{Name: "echo"}},
	{"resources/read", mcp.ReadResourceParams{URI: "neo4j://schema"}, mcp.ReadResourceParams{URI: "plain://doc"}},
	{"prompts/get", mcp.GetPromptParams{Name: "neo4j_prompt"}, mcp.GetPromptParams{Name: "plain_prompt"}},
}

func TestScopedNeo4jGate_ListsHideInstanceFromDeniedCallers(t *testing.T) {
	callers := map[string]context.Context{
		"non-granted user": ctxWithEmail("bob@hp.fr"),
		"no email":         context.Background(),
	}
	for who, ctx := range callers {
		for _, tc := range neo4jGateListCases {
			t.Run(who+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				names := listedNames(t, f.call(t, ctx, tc.method, nil))
				if names[tc.restricted] {
					t.Fatalf("%s leaked %q to %s", tc.method, tc.restricted, who)
				}
				if !names[tc.plain] {
					t.Fatalf("%s must still list unrestricted %q, got %v", tc.method, tc.plain, names)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_ListsShowInstanceToAdminAndGrantee(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		for _, tc := range neo4jGateListCases {
			t.Run(email+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				names := listedNames(t, f.call(t, ctxWithEmail(email), tc.method, nil))
				if !names[tc.restricted] || !names[tc.plain] {
					t.Fatalf("%s for %s must list %q and %q, got %v", tc.method, email, tc.restricted, tc.plain, names)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_CallsDeniedAreNotForwarded(t *testing.T) {
	callers := map[string]context.Context{
		"non-granted user": ctxWithEmail("bob@hp.fr"),
		"no email":         context.Background(),
	}
	for who, ctx := range callers {
		for _, tc := range neo4jGateCallCases {
			t.Run(who+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				resp := f.call(t, ctx, tc.method, tc.restricted)
				if resp.Error == nil || resp.Error.Message != Neo4jAccessDeniedMessage {
					t.Fatalf("%s: want access-denied error, got %+v", tc.method, resp)
				}
				if got := atomic.LoadInt32(f.hits); got != 0 {
					t.Fatalf("%s: denied call reached the upstream %d time(s)", tc.method, got)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_CallsServedForAdminAndGrantee(t *testing.T) {
	for _, email := range []string{"admin@hp.fr", "alice@hp.fr"} {
		for _, tc := range neo4jGateCallCases {
			t.Run(email+" "+tc.method, func(t *testing.T) {
				f := newNeo4jGateFixture(t, true)
				resp := f.call(t, ctxWithEmail(email), tc.method, tc.restricted)
				if resp.Error != nil {
					t.Fatalf("%s for %s: unexpected error %+v", tc.method, email, resp.Error)
				}
				if got := atomic.LoadInt32(f.hits); got != 1 {
					t.Fatalf("%s for %s: want 1 upstream hit, got %d", tc.method, email, got)
				}
			})
		}
	}
}

func TestScopedNeo4jGate_UnrestrictedBackendUnaffected(t *testing.T) {
	for _, tc := range neo4jGateCallCases {
		t.Run(tc.method, func(t *testing.T) {
			f := newNeo4jGateFixture(t, true)
			resp := f.call(t, ctxWithEmail("bob@hp.fr"), tc.method, tc.plain)
			if resp.Error != nil {
				t.Fatalf("%s on unrestricted backend: unexpected error %+v", tc.method, resp.Error)
			}
			if got := atomic.LoadInt32(f.hits); got != 1 {
				t.Fatalf("%s on unrestricted backend: want 1 upstream hit, got %d", tc.method, got)
			}
		})
	}
}

func TestScopedNeo4jGate_NilGateKeepsLegacyBehaviour(t *testing.T) {
	f := newNeo4jGateFixture(t, false)
	names := listedNames(t, f.call(t, ctxWithEmail("bob@hp.fr"), "tools/list", nil))
	if !names["neo4jprod_read_neo4j_cypher"] {
		t.Fatalf("without a wired gate every allowed backend stays visible, got %v", names)
	}
	resp := f.call(t, ctxWithEmail("bob@hp.fr"), "tools/call", mcp.CallToolParams{Name: "neo4jprod_read_neo4j_cypher"})
	if resp.Error != nil {
		t.Fatalf("without a wired gate the call must be forwarded, got %+v", resp.Error)
	}
}

func TestScopedNeo4jGate_GrantRevocationAppliesOnNextRequest(t *testing.T) {
	f := newNeo4jGateFixture(t, true)
	ctx := ctxWithEmail("alice@hp.fr")
	if !listedNames(t, f.call(t, ctx, "tools/list", nil))["neo4jprod_read_neo4j_cypher"] {
		t.Fatal("alice must see the instance while her grant exists")
	}
	delete(f.grants.grants["srv-neo4j"], "alice@hp.fr")
	if listedNames(t, f.call(t, ctx, "tools/list", nil))["neo4jprod_read_neo4j_cypher"] {
		t.Fatal("revoked grant must hide the instance on the next request")
	}
	resp := f.call(t, ctx, "tools/call", mcp.CallToolParams{Name: "neo4jprod_read_neo4j_cypher"})
	if resp.Error == nil || resp.Error.Message != Neo4jAccessDeniedMessage {
		t.Fatalf("revoked grant must deny the call, got %+v", resp)
	}
}

// initializeInstructions returns the composed `instructions` field of an
// initialize response built over f's backends with the given instructions.
func (f *neo4jGateFixture) initializeInstructions(t *testing.T, ctx context.Context, instructions []InstructionView) string {
	t.Helper()
	sg := NewScopedGateway(f.gw, map[string]bool{"srv-neo4j": true, "srv-plain": true}, nil, instructions)
	resp := sg.Handle(ctx, &mcp.Request{JSONRPC: "2.0", ID: json.RawMessage(`1`), Method: "initialize"})
	if resp == nil || resp.Error != nil {
		t.Fatalf("initialize: unexpected error response: %+v", resp)
	}
	var out mcp.InitializeResult
	if err := json.Unmarshal(resp.Result, &out); err != nil {
		t.Fatalf("unmarshal initialize result: %v", err)
	}
	return out.Instructions
}

func TestScopedNeo4jGate_InitializeOmitsInstructionsOfHiddenInstance(t *testing.T) {
	instructions := []InstructionView{
		{ID: "i-general", Title: "General", Body: "<p>general rules</p>", Kind: db.LLMInstructionRowKindGeneral},
		{ID: "i-neo4j", Title: "Neo4j schema", Body: "<p>graph schema secret</p>", Kind: db.LLMInstructionRowKindPerServer, ServerIDs: []string{"srv-neo4j"}},
		{ID: "i-plain", Title: "Plain", Body: "<p>plain usage</p>", Kind: db.LLMInstructionRowKindPerServer, ServerIDs: []string{"srv-plain"}},
		{ID: "i-both", Title: "Both", Body: "<p>shared usage</p>", Kind: db.LLMInstructionRowKindPerServer, ServerIDs: []string{"srv-neo4j", "srv-plain"}},
	}
	cases := []struct {
		who        string
		ctx        context.Context
		wantHidden bool
	}{
		{"non-granted user", ctxWithEmail("bob@hp.fr"), true},
		{"no email", context.Background(), true},
		{"admin", ctxWithEmail("admin@hp.fr"), false},
		{"grantee", ctxWithEmail("alice@hp.fr"), false},
	}
	for _, tc := range cases {
		t.Run(tc.who, func(t *testing.T) {
			f := newNeo4jGateFixture(t, true)
			got := f.initializeInstructions(t, tc.ctx, instructions)
			for _, always := range []string{"general rules", "plain usage", "shared usage"} {
				if !strings.Contains(got, always) {
					t.Fatalf("initialize for %s must keep %q, got %q", tc.who, always, got)
				}
			}
			if hidden := !strings.Contains(got, "graph schema secret"); hidden != tc.wantHidden {
				t.Fatalf("initialize for %s: per_server instruction of srv-neo4j hidden=%t, want %t (got %q)", tc.who, hidden, tc.wantHidden, got)
			}
		})
	}
}

func TestNewScopedGateway_CopiesNeo4jAccess(t *testing.T) {
	gw := New("gw", "1.0", NewRegistry())
	a := NewNeo4jAccess(nil, nil, nil, nil)
	gw.SetNeo4jAccess(a)
	if sg := NewScopedGateway(gw, nil, nil, nil); sg.neo4jAccess != a {
		t.Fatal("NewScopedGateway must copy the gateway's Neo4jAccess")
	}
}
