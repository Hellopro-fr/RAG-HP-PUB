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
// Leexi API: GET /calls?page={page}&per_page={perPage}
func (c *Client) ListCalls(ctx context.Context, page, perPage int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("page", strconv.Itoa(page))
	q.Set("per_page", strconv.Itoa(perPage))
	return c.doGet(ctx, "/calls?"+q.Encode())
}

// SearchCalls retrieves calls filtered by optional date range and pagination.
// Leexi API: GET /calls with query params.
func (c *Client) SearchCalls(ctx context.Context, startDate, endDate string, page, perPage int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("page", strconv.Itoa(page))
	q.Set("per_page", strconv.Itoa(perPage))
	if startDate != "" {
		q.Set("start_date", startDate)
	}
	if endDate != "" {
		q.Set("end_date", endDate)
	}
	return c.doGet(ctx, "/calls?"+q.Encode())
}

// GetCall retrieves full details of a call/meeting by UUID.
// The response includes transcript (word-level + paragraph-level timestamps),
// topics, and summary.
// Leexi API: GET /calls/{uuid}
func (c *Client) GetCall(ctx context.Context, callUUID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/calls/%s", callUUID)
	return c.doGet(ctx, path)
}
