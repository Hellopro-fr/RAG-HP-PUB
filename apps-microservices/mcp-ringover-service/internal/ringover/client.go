package ringover

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"time"
)

// dateOnlyRe matches "YYYY-MM-DD" without a time component.
var dateOnlyRe = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

// normalizeDate converts "YYYY-MM-DD" to full ISO 8601 ("YYYY-MM-DDT00:00:00.000Z").
// If asEndOfDay is true, it uses 23:59:59.999Z instead. Already-full timestamps are
// returned as-is.
func normalizeDate(date string, asEndOfDay bool) string {
	if dateOnlyRe.MatchString(date) {
		if asEndOfDay {
			return date + "T23:59:59.999Z"
		}
		return date + "T00:00:00.000Z"
	}
	return date
}

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

func (c *Client) doRequest(ctx context.Context, method, path string, body []byte) (json.RawMessage, error) {
	rawURL := c.baseURL + path

	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(ctx, method, rawURL, reader)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Authorization", c.apiKey)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("API error %d: %s", resp.StatusCode, string(respBody))
	}

	return json.RawMessage(respBody), nil
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

// AdvancedCallsFilter holds the advanced sub-filter accepted by POST /calls.
// Only the fields we currently use are modelled.
type AdvancedCallsFilter struct {
	Users []int `json:"users,omitempty"`
}

// PostCallsRequest is the JSON body accepted by POST /calls.
// Ringover's GET /calls has no user-filter parameter; POST /calls with
// filter="ADVANCED" and advanced.users=[ids] is the only way to scope results
// to a specific set of agents server-side.
type PostCallsRequest struct {
	Filter      string               `json:"filter,omitempty"`
	StartDate   string               `json:"start_date,omitempty"`
	EndDate     string               `json:"end_date,omitempty"`
	CallType    []string             `json:"call_type,omitempty"`
	LimitCount  int                  `json:"limit_count,omitempty"`
	LimitOffset int                  `json:"limit_offset,omitempty"`
	Advanced    *AdvancedCallsFilter `json:"advanced,omitempty"`
}

// PostCalls retrieves calls using Ringover's advanced-filter endpoint.
// Dates follow the same ISO 8601 / YYYY-MM-DD tolerance as GetCalls — short
// dates are normalised to full timestamps.
func (c *Client) PostCalls(ctx context.Context, body PostCallsRequest) (json.RawMessage, error) {
	if body.StartDate != "" {
		body.StartDate = normalizeDate(body.StartDate, false)
	}
	if body.EndDate != "" {
		body.EndDate = normalizeDate(body.EndDate, true)
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal PostCallsRequest: %w", err)
	}
	return c.doRequest(ctx, http.MethodPost, "/calls", raw)
}

// ListCallsByDate retrieves calls within a date range.
// startDate, endDate: ISO 8601 (e.g. "2026-04-01T00:00:00.000Z") or "YYYY-MM-DD".
// Short dates are automatically normalized to full ISO 8601.
func (c *Client) ListCallsByDate(ctx context.Context, startDate, endDate string, limitCount int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("start_date", normalizeDate(startDate, false))
	q.Set("end_date", normalizeDate(endDate, true))
	q.Set("limit_count", strconv.Itoa(limitCount))
	return c.doGet(ctx, "/calls?"+q.Encode())
}

// SearchCalls retrieves calls matching optional filters.
// callType: Ringover call_type filter — "ANSWERED", "MISSED", "OUT", or "VOICEMAIL" (empty = all).
// phoneNumber: filter by caller/callee number (empty = no filter).
// userID: filter by Ringover user ID (empty = all users).
func (c *Client) SearchCalls(ctx context.Context, callType, phoneNumber, userID string, limitCount int) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("limit_count", strconv.Itoa(limitCount))
	if callType != "" {
		q.Set("call_type", callType)
	}
	if phoneNumber != "" {
		q.Set("from_number", phoneNumber)
	}
	if userID != "" {
		q.Set("user_id", userID)
	}
	return c.doGet(ctx, "/calls?"+q.Encode())
}

// GetCallStatsByUser retrieves call statistics broken down by team member.
// Ringover API: GET /stats/team
// startDate, endDate: ISO 8601 or "YYYY-MM-DD".
// userID: optional — filter to a specific user (empty = all users).
func (c *Client) GetCallStatsByUser(ctx context.Context, startDate, endDate, userID string) (json.RawMessage, error) {
	q := url.Values{}
	q.Set("start_date", startDate)
	q.Set("end_date", endDate)
	if userID != "" {
		q.Set("user_id", userID)
	}
	return c.doGet(ctx, "/stats/team?"+q.Encode())
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
