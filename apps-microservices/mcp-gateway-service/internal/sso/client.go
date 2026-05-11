package sso

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client is an OAuth 2.1 confidential client for account-service. Browser-facing
// redirects use AccountPublicURL; server-to-server token exchange + revocation
// use AccountInternalURL (in-cluster, may be the same value as the public URL
// when nginx proxies both directions).
type Client struct {
	ClientID           string
	ClientSecret       string
	AccountPublicURL   string
	AccountInternalURL string
	RedirectURI        string
	Scope              string
	HTTP               *http.Client
}

// TokenResponse mirrors the JSON returned by account-service /token for both
// authorization_code and refresh_token grants.
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
	RefreshExpiresIn int `json:"refresh_expires_in,omitempty"`
	Scope        string `json:"scope,omitempty"`
}

// BuildAuthorizeURL constructs the browser-facing /authorize URL. Caller is
// responsible for storing the verifier for code_challenge in the pending cookie.
func (c *Client) BuildAuthorizeURL(challenge, state string) (string, error) {
	if c.AccountPublicURL == "" {
		return "", fmt.Errorf("AccountPublicURL not set")
	}
	u, err := url.Parse(c.AccountPublicURL + "/authorize")
	if err != nil {
		return "", fmt.Errorf("parse: %w", err)
	}
	q := u.Query()
	q.Set("response_type", "code")
	q.Set("client_id", c.ClientID)
	q.Set("redirect_uri", c.RedirectURI)
	q.Set("scope", c.Scope)
	q.Set("code_challenge", challenge)
	q.Set("code_challenge_method", "S256")
	q.Set("state", state)
	u.RawQuery = q.Encode()
	return u.String(), nil
}

// ExchangeCode swaps the authorization_code for access+refresh tokens. The
// PKCE verifier proves the caller is the same client that initiated the flow.
func (c *Client) ExchangeCode(ctx context.Context, code, verifier, redirectURI string) (*TokenResponse, error) {
	form := url.Values{}
	form.Set("grant_type", "authorization_code")
	form.Set("code", code)
	form.Set("redirect_uri", redirectURI)
	form.Set("client_id", c.ClientID)
	form.Set("client_secret", c.ClientSecret)
	form.Set("code_verifier", verifier)
	return c.doToken(ctx, form)
}

// Refresh rotates the refresh token at /token. account-service implements
// refresh-token rotation per the parent SSO spec, so the new refresh_token
// must replace the old one in the session row.
func (c *Client) Refresh(ctx context.Context, refreshToken string) (*TokenResponse, error) {
	form := url.Values{}
	form.Set("grant_type", "refresh_token")
	form.Set("refresh_token", refreshToken)
	form.Set("client_id", c.ClientID)
	form.Set("client_secret", c.ClientSecret)
	return c.doToken(ctx, form)
}

// Revoke calls /token/revoke for either an access or a refresh token. Used on
// user-initiated logout; account-service deletes the corresponding refresh row
// + emits no further access tokens for the now-revoked grant.
func (c *Client) Revoke(ctx context.Context, token, hint string) error {
	if c.AccountInternalURL == "" {
		return fmt.Errorf("AccountInternalURL not set")
	}
	form := url.Values{}
	form.Set("token", token)
	if hint != "" {
		form.Set("token_type_hint", hint)
	}
	form.Set("client_id", c.ClientID)
	form.Set("client_secret", c.ClientSecret)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.AccountInternalURL+"/token/revoke", strings.NewReader(form.Encode()))
	if err != nil {
		return fmt.Errorf("build req: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := c.client().Do(req)
	if err != nil {
		return fmt.Errorf("revoke: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("revoke status %d: %s", resp.StatusCode, string(body))
	}
	return nil
}

func (c *Client) doToken(ctx context.Context, form url.Values) (*TokenResponse, error) {
	if c.AccountInternalURL == "" {
		return nil, fmt.Errorf("AccountInternalURL not set")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.AccountInternalURL+"/token", strings.NewReader(form.Encode()))
	if err != nil {
		return nil, fmt.Errorf("build req: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")
	resp, err := c.client().Do(req)
	if err != nil {
		return nil, fmt.Errorf("token: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("token status %d: %s", resp.StatusCode, string(body))
	}
	var tr TokenResponse
	if err := json.Unmarshal(body, &tr); err != nil {
		return nil, fmt.Errorf("parse token resp: %w", err)
	}
	if tr.AccessToken == "" || tr.RefreshToken == "" {
		return nil, fmt.Errorf("token response missing required fields")
	}
	return &tr, nil
}

func (c *Client) client() *http.Client {
	if c.HTTP != nil {
		return c.HTTP
	}
	return &http.Client{Timeout: 10 * time.Second}
}
