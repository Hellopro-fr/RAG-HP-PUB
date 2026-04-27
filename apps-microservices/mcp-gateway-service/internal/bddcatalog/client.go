package bddcatalog

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

// Client is the gateway-side wrapper around the Hellopro BDD catalog HTTP API.
// All endpoints are GET-only; writes are not part of this client's surface.
type Client struct {
	baseURL    string
	adminToken string
	httpClient *http.Client
}

// New returns a configured Client. Both arguments may be empty — callers
// must guard with Enabled() before issuing requests.
func New(baseURL, adminToken string) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		adminToken: adminToken,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// Enabled reports whether both the base URL and admin token are configured.
// Safe to call on a nil receiver.
func (c *Client) Enabled() bool {
	return c != nil && c.baseURL != "" && c.adminToken != ""
}

// ListDatabases returns the catalog's known databases.
func (c *Client) ListDatabases(ctx context.Context) ([]Database, error) {
	body, err := c.do(ctx, "/databases", nil)
	if err != nil {
		return nil, err
	}
	var payload struct {
		Databases []Database `json:"databases"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("bdd catalog: decode databases: %w", err)
	}
	return payload.Databases, nil
}

// ListTables returns tables for a database, optionally filtered by a free-text
// search term passed through to the catalog as the "search" query parameter.
func (c *Client) ListTables(ctx context.Context, databaseID int, search string) ([]Table, error) {
	path := fmt.Sprintf("/databases/%d/tables", databaseID)
	var query url.Values
	if search != "" {
		query = url.Values{"search": []string{search}}
	}
	body, err := c.do(ctx, path, query)
	if err != nil {
		return nil, err
	}
	var payload struct {
		Tables []Table `json:"tables"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("bdd catalog: decode tables: %w", err)
	}
	return payload.Tables, nil
}

// ListFields returns the columns of a single table.
func (c *Client) ListFields(ctx context.Context, databaseID, tableID int) ([]Field, error) {
	path := fmt.Sprintf("/databases/%d/tables/%d/fields", databaseID, tableID)
	body, err := c.do(ctx, path, nil)
	if err != nil {
		return nil, err
	}
	var payload struct {
		Fields []Field `json:"fields"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("bdd catalog: decode fields: %w", err)
	}
	return payload.Fields, nil
}

// do issues an authenticated GET to baseURL+path. The query is appended
// only when non-empty so callers don't accidentally send "?search=".
func (c *Client) do(ctx context.Context, path string, query url.Values) ([]byte, error) {
	if !c.Enabled() {
		return nil, fmt.Errorf("bdd catalog: client not configured (BDD_CATALOG_BASE_URL/BDD_CATALOG_TOKEN unset)")
	}

	full := c.baseURL + path
	if len(query) > 0 {
		full += "?" + query.Encode()
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, full, nil)
	if err != nil {
		return nil, fmt.Errorf("bdd catalog: build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.adminToken)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("bdd catalog: %s: %w", path, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 5*1024*1024))
	if err != nil {
		return nil, fmt.Errorf("bdd catalog: read body: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// NOTE: upstream body included verbatim — sanitise if upstream ever echoes auth headers in errors
		return nil, fmt.Errorf("bdd catalog: status %d: %s", resp.StatusCode, truncate(body))
	}
	return body, nil
}

// truncate returns up to 200 chars of the given body for use in error
// messages. Avoids dumping multi-megabyte upstream payloads into logs.
func truncate(b []byte) string {
	const max = 200
	if len(b) <= max {
		return string(b)
	}
	return string(b[:max]) + "…"
}
