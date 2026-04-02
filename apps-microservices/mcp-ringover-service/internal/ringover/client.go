package ringover

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Client wraps the Ringover public REST API.
type Client struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// NewClient creates a new Ringover API client.
func NewClient(baseURL, apiKey string) *Client {
	return &Client{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// doGet performs an authenticated GET request and returns the raw JSON body.
func (c *Client) doGet(ctx context.Context, path string) (json.RawMessage, error) {
	return c.doRequest(ctx, http.MethodGet, path, nil)
}

func (c *Client) doRequest(ctx context.Context, method, path string, _ []byte) (json.RawMessage, error) {
	url := c.baseURL + path

	req, err := http.NewRequestWithContext(ctx, method, url, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Authorization", c.apiKey)
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

// GetCalls retrieves a list of calls.
func (c *Client) GetCalls(ctx context.Context, limitCount int) (json.RawMessage, error) {
	path := fmt.Sprintf("/calls?limit_count=%d", limitCount)
	return c.doGet(ctx, path)
}

// GetCallDetails retrieves details for a specific call.
func (c *Client) GetCallDetails(ctx context.Context, callID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/calls/%s", callID)
	return c.doGet(ctx, path)
}

// GetEmpowerCallUUID converts a Ringover channel_id to an Empower calluuid.
// Requires Empower to be enabled on the API key.
// Ringover API: GET /empower/platform/{platformName}/channel/{channelID}
func (c *Client) GetEmpowerCallUUID(ctx context.Context, platformName, channelID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/empower/platform/%s/channel/%s", platformName, channelID)
	return c.doGet(ctx, path)
}

// GetCallTranscription retrieves the transcription for a call.
func (c *Client) GetCallTranscription(ctx context.Context, callUUID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/empower/call/%s", callUUID)
	return c.doGet(ctx, path)
}

// GetCallSummary retrieves the AI-generated summary of a call.
func (c *Client) GetCallSummary(ctx context.Context, callUUID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/empower/call/%s/summary", callUUID)
	return c.doGet(ctx, path)
}

// GetCallMoments retrieves key moments from a call.
func (c *Client) GetCallMoments(ctx context.Context, callUUID string) (json.RawMessage, error) {
	path := fmt.Sprintf("/empower/call/%s/moments", callUUID)
	return c.doGet(ctx, path)
}

// GetContacts retrieves the list of contacts.
func (c *Client) GetContacts(ctx context.Context) (json.RawMessage, error) {
	return c.doGet(ctx, "/contacts")
}

// GetUsers retrieves the list of Ringover users.
func (c *Client) GetUsers(ctx context.Context) (json.RawMessage, error) {
	return c.doGet(ctx, "/users")
}
