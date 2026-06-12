// Package gatewaysync pushes account-service users to the MCP gateway's
// internal user sync endpoint so they are pre-provisioned as gateway users
// with the config-only role. Counterpart of the gateway's handleUserSync.
package gatewaysync

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// SyncUser is one user in the sync batch. Field names mirror the gateway's
// syncUserEntry contract.
type SyncUser struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

// Result mirrors the gateway's syncUsersResponse.
type Result struct {
	Created []string `json:"created"`
	Skipped []string `json:"skipped"`
}

type Client struct {
	baseURL string
	token   string
	cli     *http.Client
}

// New returns a client for the gateway at baseURL authenticating with the
// shared internal admin token (sent as X-Admin-Token).
func New(baseURL, token string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		cli:     &http.Client{Timeout: 5 * time.Second},
	}
}

// SyncUsers POSTs the batch to the gateway and returns its created/skipped
// outcome. Any non-200 response is an error carrying the status and a body
// excerpt.
func (c *Client) SyncUsers(users []SyncUser) (*Result, error) {
	body, err := json.Marshal(map[string][]SyncUser{"users": users})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequest(http.MethodPost, c.baseURL+"/api/v1/internal/users/sync", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-Token", c.token)

	resp, err := c.cli.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return nil, fmt.Errorf("gateway sync: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(b)))
	}
	var out Result
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}
