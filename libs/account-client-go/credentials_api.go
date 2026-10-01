package accountclient

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// GetCredentialsFromAPI fetches (clientID, clientSecret) from
// account-service over HTTP. Calls
//
//	GET {baseURL}/internal/credentials/{serviceName}
//
// with an X-Admin-Token header. The endpoint is admin-gated on the
// account-service side and decrypts the secret server-side, so this
// caller never needs MySQL access or the AES key.
//
// Empty arguments fall back to env: SERVICE_NAME, ACCOUNT_BASE_URL,
// ACCOUNT_INTERNAL_TOKEN.
func GetCredentialsFromAPI(ctx context.Context, serviceName, baseURL, adminToken string) (string, string, error) {
	if serviceName == "" {
		serviceName = strings.TrimSpace(os.Getenv("SERVICE_NAME"))
	}
	if baseURL == "" {
		baseURL = strings.TrimRight(os.Getenv("ACCOUNT_BASE_URL"), "/")
	} else {
		baseURL = strings.TrimRight(baseURL, "/")
	}
	if adminToken == "" {
		adminToken = os.Getenv("ACCOUNT_INTERNAL_TOKEN")
	}

	if serviceName == "" {
		return "", "", fmt.Errorf("service name required (or set SERVICE_NAME)")
	}
	if baseURL == "" {
		return "", "", fmt.Errorf("ACCOUNT_BASE_URL not set")
	}
	if adminToken == "" {
		return "", "", fmt.Errorf("ACCOUNT_INTERNAL_TOKEN not set")
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
