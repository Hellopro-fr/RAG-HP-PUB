package api

import "testing"

func TestOAuth2DTOStructs(t *testing.T) {
	// Validates DTO struct fields are correctly defined.
	req := CreateOAuth2ClientRequest{
		Name:      "test",
		ServerIDs: []string{"srv-1"},
	}
	if req.Name != "test" {
		t.Fatal("unexpected name")
	}

	resp := OAuth2ClientResponse{
		ID:             "client-1",
		Name:           "test",
		AccessTokenTTL: 3600,
	}
	if resp.AccessTokenTTL != 3600 {
		t.Fatal("unexpected TTL")
	}
}
