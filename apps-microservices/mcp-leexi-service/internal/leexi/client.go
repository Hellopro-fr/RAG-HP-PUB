package leexi

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// Client wraps the Leexi public REST API.
// Auth: HTTP Basic Authentication (KEY_ID:KEY_SECRET base64-encoded).
type Client struct {
	baseURL    string
	authHeader string
	httpClient *http.Client
}

// NewClient creates a new Leexi API client.
func NewClient(baseURL, keyID, keySecret string) *Client {
	encoded := base64.StdEncoding.EncodeToString([]byte(keyID + ":" + keySecret))
	return &Client{
		baseURL:    baseURL,
		authHeader: "Basic " + encoded,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// doGet performs an authenticated GET request and returns the raw JSON body.
func (c *Client) doGet(ctx context.Context, path string) (json.RawMessage, error) {
	rawURL := c.baseURL + path

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Authorization", c.authHeader)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("API error %d: %s", resp.StatusCode, string(body))
	}

	return json.RawMessage(body), nil
}

// ListCalls retrieves a paginated list of calls and meetings.
// Leexi API: GET /calls?page={page}&items={items}
func (c *Client) ListCalls(ctx context.Context, page, items int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("page", strconv.Itoa(page))
	q.Set("items", strconv.Itoa(items))
	return c.doGet(ctx, "/calls?"+q.Encode())
}

// SearchCalls retrieves calls filtered by optional date range, ordering, and pagination.
// Leexi API: GET /calls with query params.
// from/to: ISO 8601 dates (e.g. "2026-04-01T00:00:00.000Z").
// order: sorting (e.g. "created_at desc", "performed_at asc").
// ownerUUIDs: filter by one or many call owners (repeated owner_uuid[] params).
// withTranscript: include simple_transcript in list response.
func (c *Client) SearchCalls(ctx context.Context, from, to, order string, ownerUUIDs []string, withTranscript bool, page, items int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("page", strconv.Itoa(page))
	q.Set("items", strconv.Itoa(items))
	if from != "" {
		q.Set("from", from)
	}
	if to != "" {
		q.Set("to", to)
	}
	if order != "" {
		q.Set("order", order)
	}
	for _, uuid := range ownerUUIDs {
		if uuid != "" {
			q.Add("owner_uuid[]", uuid)
		}
	}
	if withTranscript {
		q.Set("with_simple_transcript", "true")
	}
	return c.doGet(ctx, "/calls?"+q.Encode())
}

// ListUsers retrieves a paginated list of users in the Leexi workspace.
// Leexi API: GET /users?page={page}&items={items}
// Returns the raw JSON for flexibility; use DecodeUsers to extract typed [User].
func (c *Client) ListUsers(ctx context.Context, page, items int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("page", strconv.Itoa(page))
	q.Set("items", strconv.Itoa(items))
	return c.doGet(ctx, "/users?"+q.Encode())
}

// GetCall retrieves full details of a call/meeting by UUID.
// The response includes transcript (word-level + paragraph-level timestamps),
// call_topics, prompts (AI summaries), and chapters.
// Leexi API: GET /calls/{uuid}
func (c *Client) GetCall(ctx context.Context, callUUID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/calls/%s", callUUID)
	return c.doGet(ctx, path)
}
