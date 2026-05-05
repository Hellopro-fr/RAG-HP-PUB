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

// FetchCredentialsFromAPI mirrors libs/account-client-go.GetCredentialsFromAPI.
// We inline a small copy here instead of taking a module-replace dependency
// on libs/account-client-go: the function is 40 lines, has no exotic deps,
// and avoids monorepo go.mod replace plumbing for a single caller.
//
// Calls GET {baseURL}/internal/credentials/{serviceName} with X-Admin-Token.
// Returns (client_id, client_secret) or an error.
func FetchCredentialsFromAPI(ctx context.Context, serviceName, baseURL, adminToken string) (string, string, error) {
	if serviceName == "" {
		return "", "", fmt.Errorf("service name required")
	}
	baseURL = strings.TrimRight(baseURL, "/")
	if baseURL == "" {
		return "", "", fmt.Errorf("account base URL not set")
	}
	if adminToken == "" {
		return "", "", fmt.Errorf("admin token not set")
	}

	u := baseURL + "/internal/credentials/" + url.PathEscape(serviceName)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", "", err
	}
	req.Header.Set("X-Admin-Token", adminToken)

	cli := &http.Client{Timeout: 5 * time.Second}
	resp, err := cli.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == http.StatusNotFound {
		return "", "", fmt.Errorf("no active service named %q in account-service", serviceName)
	}
	if resp.StatusCode != http.StatusOK {
		return "", "", fmt.Errorf("internal credentials endpoint returned %d: %s", resp.StatusCode, string(body))
	}
	var out struct {
		ClientID     string `json:"client_id"`
		ClientSecret string `json:"client_secret"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return "", "", fmt.Errorf("parse response: %w", err)
	}
	if out.ClientID == "" || out.ClientSecret == "" {
		return "", "", fmt.Errorf("internal credentials response missing fields")
	}
	return out.ClientID, out.ClientSecret, nil
}
