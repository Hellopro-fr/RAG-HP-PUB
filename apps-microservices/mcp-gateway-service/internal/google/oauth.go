package google

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net/http"

	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
)

// OAuthClient manages Google OAuth2 authentication for Sheets API access.
type OAuthClient struct {
	config *oauth2.Config
}

// NewOAuthClient creates a new Google OAuth2 client.
func NewOAuthClient(clientID, clientSecret, redirectURL string) *OAuthClient {
	return &OAuthClient{
		config: &oauth2.Config{
			ClientID:     clientID,
			ClientSecret: clientSecret,
			RedirectURL:  redirectURL,
			Scopes:       []string{"https://www.googleapis.com/auth/spreadsheets.readonly"},
			Endpoint:     google.Endpoint,
		},
	}
}

// BuildAuthURL generates the Google consent URL with a CSRF state parameter.
func (c *OAuthClient) BuildAuthURL(state string) string {
	return c.config.AuthCodeURL(state, oauth2.AccessTypeOffline, oauth2.SetAuthURLParam("prompt", "consent"))
}

// ExchangeCode exchanges an authorization code for tokens.
func (c *OAuthClient) ExchangeCode(ctx context.Context, code string) (*oauth2.Token, error) {
	token, err := c.config.Exchange(ctx, code)
	if err != nil {
		return nil, fmt.Errorf("exchange code: %w", err)
	}
	return token, nil
}

// BuildHTTPClient creates an authenticated HTTP client from a token.
// The client automatically refreshes the access token when it expires.
func (c *OAuthClient) BuildHTTPClient(ctx context.Context, token *oauth2.Token) *http.Client {
	return c.config.Client(ctx, token)
}

// TokenSource returns an oauth2.TokenSource that auto-refreshes using the refresh token.
func (c *OAuthClient) TokenSource(ctx context.Context, token *oauth2.Token) oauth2.TokenSource {
	return c.config.TokenSource(ctx, token)
}

// GenerateState creates a cryptographically random state string for CSRF protection.
func GenerateState() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generate state: %w", err)
	}
	return hex.EncodeToString(b), nil
}
