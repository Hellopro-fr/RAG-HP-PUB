package gateway

import (
	"context"
	"testing"

	"mcp-gateway/internal/scopetoken"
)

func identityBackend(tags ...string) *BackendServer {
	return &BackendServer{
		ID:          "srv-atb",
		Tags:        tags,
		AuthHeaders: map[string]string{"X-Agent-Gateway-Secret": "s3cret"},
	}
}

func identityCtx(clientID, email string) context.Context {
	ctx := context.Background()
	if clientID != "" {
		ctx = context.WithValue(ctx, scopetoken.ClientIDContextKey, clientID)
	}
	if email != "" {
		ctx = context.WithValue(ctx, scopetoken.EndUserEmailContextKey, email)
	}
	return ctx
}

func TestRequestHeaders_AgentIdentity_ClientCredentials(t *testing.T) {
	sg := &ScopedGateway{}
	h := sg.requestHeadersFor(identityCtx("client-42", ""), identityBackend("agent-identity"))
	if h[agentClientHeader] != "client-42" {
		t.Fatalf("client id not forwarded: %v", h)
	}
	if _, ok := h[agentEmailHeader]; ok {
		t.Fatalf("no email in a client_credentials call: %v", h)
	}
}

func TestRequestHeaders_AgentIdentity_UserEmail(t *testing.T) {
	sg := &ScopedGateway{}
	h := sg.requestHeadersFor(identityCtx("client-42", "alice@example.com"), identityBackend("agent-identity"))
	if h[agentClientHeader] != "client-42" || h[agentEmailHeader] != "alice@example.com" {
		t.Fatalf("identity headers missing: %v", h)
	}
}

func TestRequestHeaders_AgentIdentity_FlagOff_NoHeaders(t *testing.T) {
	sg := &ScopedGateway{}
	h := sg.requestHeadersFor(identityCtx("client-42", "alice@example.com"), identityBackend())
	if len(h) != 1 || h["X-Agent-Gateway-Secret"] != "s3cret" {
		t.Fatalf("untagged backend must receive only its static headers: %v", h)
	}
}

func TestRequestHeaders_AgentIdentity_StaticAuthHeadersKept(t *testing.T) {
	sg := &ScopedGateway{}
	b := identityBackend("agent-identity")
	h := sg.requestHeadersFor(identityCtx("client-42", ""), b)
	if h["X-Agent-Gateway-Secret"] != "s3cret" {
		t.Fatalf("static secret dropped: %v", h)
	}
	if _, ok := b.AuthHeaders[agentClientHeader]; ok {
		t.Fatal("the backend's static header map must not be mutated")
	}
}

// An identity value present in the static auth headers (misconfiguration) never reaches the
// backend: identity comes only from the caller's token.
func TestRequestHeaders_AgentIdentity_SpoofedStaticHeaderIgnored(t *testing.T) {
	sg := &ScopedGateway{}
	b := identityBackend("agent-identity")
	b.AuthHeaders["x-agent-client-id"] = "forged"
	b.AuthHeaders["X-Agent-User-Email"] = "forged@example.com"
	h := sg.requestHeadersFor(identityCtx("client-42", ""), b)
	for k, v := range h {
		if v == "forged" || v == "forged@example.com" {
			t.Fatalf("forged identity forwarded via %s: %v", k, h)
		}
	}
	if h[agentClientHeader] != "client-42" {
		t.Fatalf("real identity missing: %v", h)
	}
}

func TestRequestHeaders_AgentIdentity_FullAccessGrantStillInjects(t *testing.T) {
	sg := &ScopedGateway{
		serverAuth: &fakeServerAuth{grants: map[string]map[string]bool{
			"srv-atb": {"alice@example.com": true},
		}},
	}
	h := sg.requestHeadersFor(identityCtx("client-42", "alice@example.com"), identityBackend("agent-identity"))
	if h[agentClientHeader] != "client-42" || h[agentEmailHeader] != "alice@example.com" {
		t.Fatalf("full-access grant must keep the identity headers: %v", h)
	}
}
