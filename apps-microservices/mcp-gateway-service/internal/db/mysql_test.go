package db

import "testing"

func TestTableNames(t *testing.T) {
	tests := []struct {
		model    interface{ TableName() string }
		expected string
	}{
		{MCPServer{}, "mcp_servers"},
		{ServerTool{}, "server_tools"},
		{ServerResource{}, "server_resources"},
		{ServerPrompt{}, "server_prompts"},
		{PromptArgument{}, "prompt_arguments"},
		{ServerTag{}, "server_tags"},
		{ScopeToken{}, "scope_tokens"},
		{ScopeTokenServer{}, "scope_token_servers"},
		{ScopeTokenTool{}, "scope_token_tools"},
		{OAuth2Client{}, "oauth2_clients"},
		{OAuth2ClientServer{}, "oauth2_client_servers"},
		{OAuth2ClientTool{}, "oauth2_client_tools"},
		{OAuth2AuthorizationCode{}, "oauth2_authorization_codes"},
		{OAuth2RefreshToken{}, "oauth2_refresh_tokens"},
		{OAuth2Consent{}, "oauth2_consents"},
	}
	for _, tt := range tests {
		if got := tt.model.TableName(); got != tt.expected {
			t.Errorf("TableName() = %q, want %q", got, tt.expected)
		}
	}
}
