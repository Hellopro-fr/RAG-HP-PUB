// Package ringoveradmin provides an internal HTTP client for the
// mcp-ringover-service /admin/* endpoints. It mirrors the leexiadmin client
// but speaks Ringover's integer user-ID model instead of UUIDs.
package ringoveradmin

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

// User mirrors the typed payload returned by mcp-ringover-service /admin/users.
// Ringover identifies users with numeric integer IDs (not UUIDs). Only the
// fields used by the gateway are decoded.
type User struct {
	UserID    int    `json:"user_id"`
	TeamID    int    `json:"team_id,omitempty"`
	TeamName  string `json:"team_name,omitempty"`
	FirstName string `json:"firstname,omitempty"`
	LastName  string `json:"lastname,omitempty"`
	Email     string `json:"email,omitempty"`
}

// Team is the lightweight team view derived by mcp-ringover-service.
type Team struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

// Client is the gateway-side wrapper around mcp-ringover-service /admin/*.
type Client struct {
	baseURL    string
	adminToken string
	httpClient *http.Client

	mu         sync.RWMutex
	cachedAt   time.Time
	cachedUsrs []User
}

// cacheTTL matches the leexiadmin cache — picker latency vs. workspace freshness.
const cacheTTL = 5 * time.Minute

// NewClient returns a configured client. baseURL must be the in-cluster URL
// of mcp-ringover-service (e.g. http://mcp-ringover-service:8586). When
// either argument is empty the client is considered disabled and its methods
// return an error.
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

// ListUsers fetches the user list from mcp-ringover-service. forceRefresh
// skips the cache for one call.
func (c *Client) ListUsers(ctx context.Context, forceRefresh bool) ([]User, error) {
	if !c.Enabled() {
		return nil, fmt.Errorf("ringoveradmin: RINGOVER_INTERNAL_URL and RINGOVER_ADMIN_TOKEN must both be set")
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
		return nil, fmt.Errorf("ringoveradmin: decode users: %w", err)
	}

	c.mu.Lock()
	c.cachedUsrs = payload.Users
	c.cachedAt = time.Now()
	c.mu.Unlock()

	return payload.Users, nil
}

// ListTeams fetches the team list, derived from the cached user list whenever
// possible so we avoid a redundant upstream round-trip.
func (c *Client) ListTeams(ctx context.Context, forceRefresh bool) ([]Team, error) {
	users, err := c.ListUsers(ctx, forceRefresh)
	if err != nil {
		return nil, err
	}

	seen := map[int]Team{}
	for _, u := range users {
		if u.TeamID == 0 {
			continue
		}
		if _, ok := seen[u.TeamID]; !ok {
			seen[u.TeamID] = Team{ID: u.TeamID, Name: u.TeamName}
		}
	}
	teams := make([]Team, 0, len(seen))
	for _, t := range seen {
		teams = append(teams, t)
	}
	return teams, nil
}

// ResolveTeamMembers expands a slice of team IDs into the union of their
// members' user IDs. Used by the runtime header injection for tokens whose
// RingoverFilterMode is "teams".
func (c *Client) ResolveTeamMembers(ctx context.Context, teamIDs []int) ([]int, error) {
	if len(teamIDs) == 0 {
		return nil, nil
	}
	users, err := c.ListUsers(ctx, false)
	if err != nil {
		return nil, err
	}
	want := make(map[int]struct{}, len(teamIDs))
	for _, id := range teamIDs {
		want[id] = struct{}{}
	}
	out := make([]int, 0)
	for _, u := range users {
		if _, ok := want[u.TeamID]; ok {
			out = append(out, u.UserID)
		}
	}
	return out, nil
}

// FindUserByEmail returns the Ringover user whose email matches (case-insensitive).
// Used by token creation when RingoverFilterMode is "creator".
func (c *Client) FindUserByEmail(ctx context.Context, email string) (*User, error) {
	if email == "" {
		return nil, fmt.Errorf("ringoveradmin: empty email")
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
	return nil, fmt.Errorf("ringoveradmin: no Ringover user matches email %q", email)
}

// do issues an authenticated GET request to the configured base URL.
func (c *Client) do(ctx context.Context, path string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return nil, fmt.Errorf("ringoveradmin: build request: %w", err)
	}
	req.Header.Set("X-Admin-Token", c.adminToken)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("ringoveradmin: %s: %w", path, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 5*1024*1024))
	if err != nil {
		return nil, fmt.Errorf("ringoveradmin: read body: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("ringoveradmin: %s: HTTP %d: %s", path, resp.StatusCode, string(body))
	}
	return body, nil
}
