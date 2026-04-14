// Package leexiadmin provides an internal HTTP client for the
// mcp-leexi-service /admin/* endpoints. It is the single place where the
// gateway resolves Leexi users and teams used by the token filter UI and by
// the runtime owner-scope enforcement.
package leexiadmin

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// User mirrors the typed payload returned by mcp-leexi-service /admin/users.
// Field names intentionally match the upstream service to avoid translation
// noise; only the fields used by the gateway are decoded.
type User struct {
	UUID      string `json:"uuid"`
	Email     string `json:"email,omitempty"`
	FirstName string `json:"first_name,omitempty"`
	LastName  string `json:"last_name,omitempty"`
	TeamUUID  string `json:"team_uuid,omitempty"`
	TeamName  string `json:"team_name,omitempty"`
}

// Team is the lightweight team view derived by mcp-leexi-service.
type Team struct {
	UUID string `json:"uuid"`
	Name string `json:"name"`
}

// Client is the gateway-side wrapper around mcp-leexi-service /admin/*.
// It exposes a small in-memory cache (5 min TTL) so the picker UI stays snappy
// and runtime header injection doesn't hit the upstream on every request.
type Client struct {
	baseURL    string
	adminToken string
	httpClient *http.Client

	mu         sync.RWMutex
	cachedAt   time.Time
	cachedUsrs []User
}

// cacheTTL is the in-memory freshness window for the user list. Five minutes
// is a pragmatic balance between picker latency and reflecting workspace
// changes without requiring an explicit cache-invalidation API.
const cacheTTL = 5 * time.Minute

// NewClient returns a configured client. baseURL must be the in-cluster URL
// of mcp-leexi-service (e.g. http://mcp-leexi-service:8589). When either
// argument is empty the client is considered disabled and its methods will
// return an error explaining the misconfiguration.
func NewClient(baseURL, adminToken string) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		adminToken: adminToken,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

// Enabled reports whether the client has both a base URL and an admin token.
func (c *Client) Enabled() bool {
	return c != nil && c.baseURL != "" && c.adminToken != ""
}

// ListUsers fetches the user list from mcp-leexi-service. Results are cached
// in-process for cacheTTL. forceRefresh skips the cache for one call.
func (c *Client) ListUsers(ctx context.Context, forceRefresh bool) ([]User, error) {
	if !c.Enabled() {
		return nil, fmt.Errorf("leexiadmin: LEEXI_INTERNAL_URL and LEEXI_ADMIN_TOKEN must both be set")
	}

	if !forceRefresh {
		c.mu.RLock()
		if time.Since(c.cachedAt) < cacheTTL && c.cachedUsrs != nil {
			users := c.cachedUsrs
			c.mu.RUnlock()
			return users, nil
		}
		c.mu.RUnlock()
	}

	body, err := c.do(ctx, "/admin/users")
	if err != nil {
		return nil, err
	}

	var payload struct {
		Users []User `json:"users"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("leexiadmin: decode users: %w", err)
	}

	c.mu.Lock()
	c.cachedUsrs = payload.Users
	c.cachedAt = time.Now()
	c.mu.Unlock()

	return payload.Users, nil
}

// ListTeams fetches the team list. Internally derived from the cached user
// list whenever possible to avoid a redundant upstream round trip.
func (c *Client) ListTeams(ctx context.Context, forceRefresh bool) ([]Team, error) {
	users, err := c.ListUsers(ctx, forceRefresh)
	if err != nil {
		return nil, err
	}

	seen := map[string]Team{}
	for _, u := range users {
		if u.TeamUUID == "" {
			continue
		}
		if _, ok := seen[u.TeamUUID]; !ok {
			seen[u.TeamUUID] = Team{UUID: u.TeamUUID, Name: u.TeamName}
		}
	}
	teams := make([]Team, 0, len(seen))
	for _, t := range seen {
		teams = append(teams, t)
	}
	return teams, nil
}

// ResolveTeamMembers expands a slice of team UUIDs into the union of their
// members' user UUIDs. Used by the runtime header injection for tokens whose
// LeexiFilterMode is "teams".
func (c *Client) ResolveTeamMembers(ctx context.Context, teamUUIDs []string) ([]string, error) {
	if len(teamUUIDs) == 0 {
		return nil, nil
	}
	users, err := c.ListUsers(ctx, false)
	if err != nil {
		return nil, err
	}
	want := make(map[string]struct{}, len(teamUUIDs))
	for _, id := range teamUUIDs {
		want[id] = struct{}{}
	}
	out := make([]string, 0)
	for _, u := range users {
		if _, ok := want[u.TeamUUID]; ok {
			out = append(out, u.UUID)
		}
	}
	return out, nil
}

// FindUserByEmail returns the Leexi user whose email matches (case-insensitive).
// Used by token creation when LeexiFilterMode is "creator" to translate the
// Hellopro session email into a Leexi UUID.
func (c *Client) FindUserByEmail(ctx context.Context, email string) (*User, error) {
	if email == "" {
		return nil, fmt.Errorf("leexiadmin: empty email")
	}
	users, err := c.ListUsers(ctx, false)
	if err != nil {
		return nil, err
	}
	target := strings.ToLower(email)
	for i := range users {
		if strings.ToLower(users[i].Email) == target {
			return &users[i], nil
		}
	}
	return nil, fmt.Errorf("leexiadmin: no Leexi user matches email %q", email)
}

// do issues an authenticated GET request to the configured base URL.
func (c *Client) do(ctx context.Context, path string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, fmt.Errorf("leexiadmin: build request: %w", err)
	}
	req.Header.Set("X-Admin-Token", c.adminToken)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("leexiadmin: %s: %w", path, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 5*1024*1024))
	if err != nil {
		return nil, fmt.Errorf("leexiadmin: read body: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("leexiadmin: %s: HTTP %d: %s", path, resp.StatusCode, string(body))
	}
	return body, nil
}
