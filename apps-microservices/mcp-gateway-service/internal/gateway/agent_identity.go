package gateway

import (
	"context"
	"strings"

	"mcp-gateway/internal/scopetoken"
)

// Agent identity forwarding (opt-in per backend via the "agent-identity" server tag).
//
// Backends such as agent-task-manager-backend need to know WHICH agent or user is calling,
// while the gateway terminates the caller's bearer token. For tagged backends the gateway adds:
//   - X-Agent-Client-Id:  the OAuth2 client_id (every OAuth2 grant, incl. client_credentials)
//   - X-Agent-User-Email: the end-user email (authorization_code / refresh_token grants)
//
// The backend trusts these headers only together with a shared secret the admin configures as a
// static auth header (X-Agent-Gateway-Secret) on the same backend. Values that would come from
// the static auth headers are removed first, so identity can only come from the token.
const (
	agentIdentityTag  = "agent-identity"
	agentClientHeader = "X-Agent-Client-Id"
	agentEmailHeader  = "X-Agent-User-Email"
)

func injectAgentIdentity(ctx context.Context, headers map[string]string, backend *BackendServer) {
	if !backend.HasTag(agentIdentityTag) {
		return
	}
	for k := range headers {
		if strings.EqualFold(k, agentClientHeader) || strings.EqualFold(k, agentEmailHeader) {
			delete(headers, k)
		}
	}
	if id, ok := scopetoken.ClientIDFromContext(ctx); ok {
		headers[agentClientHeader] = id
	}
	if email, ok := scopetoken.EndUserEmailFromContext(ctx); ok {
		headers[agentEmailHeader] = email
	}
}
