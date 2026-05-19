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

// ClientCredentials carries everything the gateway needs to act as an
// account-service OAuth2 client: secret material plus the registered
// redirect_uris (first element wins when SSO_REDIRECT_URI env is unset).
type ClientCredentials struct {
	ClientID     string
	ClientSecret string
	RedirectURIs []string
}

// FetchCredentialsFromAPI mirrors libs/account-client-go.GetCredentialsFromAPI.
// We inline a small copy here instead of taking a module-replace dependency
// on libs/account-client-go: the function has no exotic deps, and avoids
// monorepo go.mod replace plumbing for a single caller.
//
// Calls GET {baseURL}/internal/credentials/{serviceName} with X-Admin-Token.
// Returns (client_id, client_secret, redirect_uris) so the caller can use
// the registered redirect_uri as the source of truth instead of recomputing
// it from GATEWAY_PUBLIC_URL.
func FetchCredentialsFromAPI(ctx context.Context, serviceName, baseURL, adminToken string) (*ClientCredentials, error) {
	if serviceName == "" {
		return nil, fmt.Errorf("service name required")
	}
	baseURL = strings.TrimRight(baseURL, "/")
	if baseURL == "" {
		return nil, fmt.Errorf("account base URL not set")
	}
	if adminToken == "" {
		return nil, fmt.Errorf("admin token not set")
	}

	u := baseURL + "/internal/credentials/" + url.PathEscape(serviceName)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Admin-Token", adminToken)

	cli := &http.Client{Timeout: 5 * time.Second}
	resp, err := cli.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("no active service named %q in account-service", serviceName)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("internal credentials endpoint returned %d: %s", resp.StatusCode, string(body))
	}
	var out struct {
		ClientID     string   `json:"client_id"`
		ClientSecret string   `json:"client_secret"`
		RedirectURIs []string `json:"redirect_uris"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}
	if out.ClientID == "" || out.ClientSecret == "" {
		return nil, fmt.Errorf("internal credentials response missing fields")
	}
	return &ClientCredentials{
		ClientID:     out.ClientID,
		ClientSecret: out.ClientSecret,
		RedirectURIs: out.RedirectURIs,
	}, nil
}
