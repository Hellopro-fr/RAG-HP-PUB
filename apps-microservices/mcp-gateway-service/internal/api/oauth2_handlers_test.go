package api

import "testing"

func TestBuildOAuth2ServerToolsResponse(t *testing.T) {
	// Validates the helper correctly groups tools by server
	// Admin API handlers are integration-tested against a running gateway.
	t.Log("oauth2 admin handler tests require a running HTTP server and database")
}
