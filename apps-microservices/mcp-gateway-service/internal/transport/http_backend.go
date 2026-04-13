package transport

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/cookiejar"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/mcp"
)

// maxResponseSize is the maximum allowed response body size from a backend (10 MB).
const maxResponseSize = 10 * 1024 * 1024

// ── transport type ────────────────────────────────────────────────────────────

type backendTransport string

const (
	transportSSE            backendTransport = "sse"
	transportStreamableHTTP backendTransport = "streamable-http"
)

// BackendClient calls a remote MCP server over HTTP JSON-RPC.
// It discovers the message endpoint dynamically via Connect().
type BackendClient struct {
	sseURL       string            // base URL of the backend
	messageURL   string            // discovered or explicitly set message endpoint
	transport    backendTransport  // which transport was negotiated
	httpClient   *http.Client
	extraHeaders map[string]string // additional headers sent on every request (e.g. auth)
}

// newHTTPClient creates an http.Client that preserves auth headers across redirects.
// Go's default client strips Authorization headers on redirect for security,
// but MCP backends behind auth proxies need headers on every request.
func newHTTPClient(timeout time.Duration) *http.Client {
	// Cookie jar stores cookies set by redirect responses (e.g. session cookies
	// from auth proxies like bo.hellopro.fr that require cookie-based auth).
	jar, _ := cookiejar.New(nil)
	return &http.Client{
		Timeout: timeout,
		Jar:     jar,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 10 {
				return fmt.Errorf("stopped after 10 redirects")
			}
			// Preserve headers from the original request on redirects
			for key, vals := range via[0].Header {
				if _, exists := req.Header[key]; !exists {
					req.Header[key] = vals
				}
			}
			return nil
		},
	}
}

// NewBackendClient creates a client that will discover its message endpoint
// and transport type via Connect(). Call Connect() before use.
func NewBackendClient(sseURL string, headers map[string]string) *BackendClient {
	return &BackendClient{
		sseURL:       strings.TrimRight(sseURL, "/"),
		extraHeaders: headers,
		httpClient:   newHTTPClient(30 * time.Second),
	}
}

// NewBackendClientWithEndpoint creates a client with an already-known message
// endpoint URL. Defaults to streamable-http transport.
// Uses a longer timeout (120s) for tool calls since backends like external APIs
// may need more time to execute queries.
func NewBackendClientWithEndpoint(messageURL string, headers map[string]string) *BackendClient {
	return &BackendClient{
		messageURL:   messageURL,
		extraHeaders: headers,
		transport:    transportStreamableHTTP,
		httpClient:   newHTTPClient(120 * time.Second),
	}
}

// applyHeaders sets extra headers on an outgoing HTTP request.
func (c *BackendClient) applyHeaders(req *http.Request) {
	for k, v := range c.extraHeaders {
		req.Header.Set(k, v)
	}
}

// Connect discovers the backend's message endpoint and transport type.
//
// It tries strategies in order (streamable HTTP first since it's stateless
// and doesn't require keeping a session alive like SSE):
//  1. Streamable HTTP: POST <baseURL>/mcp
//  2. Streamable HTTP: POST <baseURL>/mcp/
//  3. SSE handshake: GET <baseURL>/sse (5s timeout) — last because SSE probe
//     creates a session that dies when the probe connection closes
func (c *BackendClient) Connect(ctx context.Context) error {
	if c.sseURL == "" {
		return fmt.Errorf("no base URL configured (use NewBackendClient)")
	}

	// 1. Try Streamable HTTP: POST /mcp
	if err := c.tryStreamableHTTP(ctx, c.sseURL+"/mcp"); err == nil {
		return nil
	} else {
		log.Printf("[backend] streamable-http probe /mcp failed for %s: %v", c.sseURL, err)
	}

	// 2. Try Streamable HTTP: POST /mcp/ (trailing slash)
	if err := c.tryStreamableHTTP(ctx, c.sseURL+"/mcp/"); err == nil {
		return nil
	} else {
		log.Printf("[backend] streamable-http probe /mcp/ failed for %s: %v", c.sseURL, err)
	}

	// 3. Try Streamable HTTP: POST directly to the base URL (some servers serve MCP at root)
	if err := c.tryStreamableHTTP(ctx, c.sseURL); err == nil {
		return nil
	} else {
		log.Printf("[backend] streamable-http probe (base URL) failed for %s: %v", c.sseURL, err)
	}

	// 4. Try base URL with trailing slash
	if err := c.tryStreamableHTTP(ctx, c.sseURL+"/"); err == nil {
		return nil
	} else {
		log.Printf("[backend] streamable-http probe (base URL/) failed for %s: %v", c.sseURL, err)
	}

	// 5. Try SSE transport (last — probe creates a session that closes immediately).
	if err := c.trySSE(ctx); err == nil {
		return nil
	} else {
		log.Printf("[backend] SSE probe failed for %s: %v", c.sseURL, err)
	}

	return fmt.Errorf("all transport probes failed for %s (tried POST /mcp, POST /mcp/, POST base, POST base/, SSE /sse)", c.sseURL)
}

// trySSE attempts an SSE handshake with a 5-second timeout.
func (c *BackendClient) trySSE(ctx context.Context) error {
	sseCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(sseCtx, http.MethodGet, c.sseURL+"/sse", nil)
	if err != nil {
		return fmt.Errorf("create SSE request: %w", err)
	}
	req.Header.Set("Accept", "text/event-stream")
	c.applyHeaders(req)

	// Use a client without default timeout — the context handles cancellation.
	sseClient := newHTTPClient(0)
	resp, err := sseClient.Do(req)
	if err != nil {
		return fmt.Errorf("SSE connect: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("SSE status %d", resp.StatusCode)
	}

	// Parse the SSE stream looking for "event: endpoint" + "data: <url>".
	scanner := bufio.NewScanner(resp.Body)
	var currentEvent string
	for scanner.Scan() {
		line := scanner.Text()

		if strings.HasPrefix(line, "event: ") {
			currentEvent = strings.TrimPrefix(line, "event: ")
			continue
		}
		if strings.HasPrefix(line, "data: ") && currentEvent == "endpoint" {
			c.messageURL = strings.TrimPrefix(line, "data: ")
			c.transport = transportSSE
			return nil
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("SSE read: %w", err)
	}

	return fmt.Errorf("SSE stream closed before sending endpoint")
}

// tryStreamableHTTP sends a probe initialize request to the given URL.
// On success it sets messageURL and transport.
func (c *BackendClient) tryStreamableHTTP(ctx context.Context, url string) error {
	probeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	probe := mcp.Request{
		JSONRPC: "2.0",
		ID:      json.RawMessage(`1`),
		Method:  "initialize",
	}
	params := mcp.InitializeParams{
		ProtocolVersion: mcp.ProtocolVersion,
		Capabilities:    mcp.ClientCapabilities{},
		ClientInfo:      mcp.Implementation{Name: "mcp-gateway-probe", Version: "0.1.0"},
	}
	b, _ := json.Marshal(params)
	probe.Params = b

	body, _ := json.Marshal(probe)

	req, err := http.NewRequestWithContext(probeCtx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	c.applyHeaders(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("http call: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("status %d", resp.StatusCode)
	}

	respBody, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseSize))
	if err != nil {
		return fmt.Errorf("read body: %w", err)
	}

	// Try to parse as a valid JSON-RPC response (handles both pure JSON and SSE-wrapped).
	rpcResp, err := parseResponseBody(respBody)
	if err != nil {
		return fmt.Errorf("parse probe response: %w", err)
	}

	// Verify it looks like a real initialize result.
	if rpcResp.Result == nil && rpcResp.Error == nil {
		return fmt.Errorf("probe response has neither result nor error")
	}

	c.messageURL = url
	c.transport = transportStreamableHTTP
	return nil
}

// MessageURL returns the discovered (or explicitly set) message endpoint.
func (c *BackendClient) MessageURL() string {
	return c.messageURL
}

// TransportType returns the negotiated transport type as a string.
func (c *BackendClient) TransportType() string {
	return string(c.transport)
}

// Call sends a JSON-RPC request to the backend and returns the raw result.
// It handles both pure JSON and SSE-wrapped response bodies.
func (c *BackendClient) Call(ctx context.Context, method string, params any) (json.RawMessage, error) {
	if c.messageURL == "" {
		return nil, fmt.Errorf("message endpoint not set — call Connect() first")
	}

	id, _ := json.Marshal(1)
	req := mcp.Request{
		JSONRPC: "2.0",
		ID:      id,
		Method:  method,
	}
	if params != nil {
		b, err := json.Marshal(params)
		if err != nil {
			return nil, fmt.Errorf("marshal params: %w", err)
		}
		req.Params = b
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.messageURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "application/json, text/event-stream")
	c.applyHeaders(httpReq)

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("http call: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseSize))
	if err != nil {
		return nil, fmt.Errorf("read response body: %w", err)
	}

	rpcResp, err := parseResponseBody(respBody)
	if err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	if rpcResp.Error != nil {
		return nil, fmt.Errorf("rpc error %d: %s", rpcResp.Error.Code, rpcResp.Error.Message)
	}

	return rpcResp.Result, nil
}

// parseResponseBody handles two response formats:
//  1. Pure JSON: body is a direct JSON-RPC response object.
//  2. SSE-wrapped: body contains "event: message\ndata: {...}\n\n",
//     where the JSON-RPC response is on the data line.
func parseResponseBody(body []byte) (*mcp.Response, error) {
	// Try pure JSON first.
	var rpcResp mcp.Response
	if err := json.Unmarshal(body, &rpcResp); err == nil {
		if rpcResp.JSONRPC == "2.0" {
			return &rpcResp, nil
		}
	}

	// Fall back to SSE-wrapped: scan for "data: " lines.
	scanner := bufio.NewScanner(bytes.NewReader(body))
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "data: ") {
			data := strings.TrimPrefix(line, "data: ")
			var sseResp mcp.Response
			if err := json.Unmarshal([]byte(data), &sseResp); err == nil {
				if sseResp.JSONRPC == "2.0" {
					return &sseResp, nil
				}
			}
		}
	}

	// Truncate body for error message readability.
	preview := string(body)
	if len(preview) > 200 {
		preview = preview[:200] + "..."
	}
	return nil, fmt.Errorf("could not parse as JSON-RPC or SSE-wrapped response: %s", preview)
}

// ── typed RPC wrappers ────────────────────────────────────────────────────────

// Initialize performs the MCP handshake with a backend server.
func (c *BackendClient) Initialize(ctx context.Context, gatewayInfo mcp.Implementation) (*mcp.InitializeResult, error) {
	params := mcp.InitializeParams{
		ProtocolVersion: mcp.ProtocolVersion,
		Capabilities:    mcp.ClientCapabilities{},
		ClientInfo:      gatewayInfo,
	}
	raw, err := c.Call(ctx, "initialize", params)
	if err != nil {
		return nil, err
	}
	var result mcp.InitializeResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse initialize result: %w", err)
	}
	return &result, nil
}

// ListTools fetches the tool list from the backend.
func (c *BackendClient) ListTools(ctx context.Context) ([]mcp.Tool, error) {
	raw, err := c.Call(ctx, "tools/list", nil)
	if err != nil {
		return nil, err
	}
	var result mcp.ListToolsResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse tools/list: %w", err)
	}
	return result.Tools, nil
}

// CallTool forwards a tool invocation to the backend.
func (c *BackendClient) CallTool(ctx context.Context, params mcp.CallToolParams) (*mcp.CallToolResult, error) {
	raw, err := c.Call(ctx, "tools/call", params)
	if err != nil {
		return nil, err
	}
	var result mcp.CallToolResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse tools/call: %w", err)
	}
	return &result, nil
}

// ListResources fetches the resource list from the backend.
func (c *BackendClient) ListResources(ctx context.Context) ([]mcp.Resource, error) {
	raw, err := c.Call(ctx, "resources/list", nil)
	if err != nil {
		return nil, err
	}
	var result mcp.ListResourcesResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse resources/list: %w", err)
	}
	return result.Resources, nil
}

// ReadResource reads a resource from the backend.
func (c *BackendClient) ReadResource(ctx context.Context, params mcp.ReadResourceParams) (*mcp.ReadResourceResult, error) {
	raw, err := c.Call(ctx, "resources/read", params)
	if err != nil {
		return nil, err
	}
	var result mcp.ReadResourceResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse resources/read: %w", err)
	}
	return &result, nil
}

// ListPrompts fetches the prompt list from the backend.
func (c *BackendClient) ListPrompts(ctx context.Context) ([]mcp.Prompt, error) {
	raw, err := c.Call(ctx, "prompts/list", nil)
	if err != nil {
		return nil, err
	}
	var result mcp.ListPromptsResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse prompts/list: %w", err)
	}
	return result.Prompts, nil
}

// GetPrompt retrieves a rendered prompt from the backend.
func (c *BackendClient) GetPrompt(ctx context.Context, params mcp.GetPromptParams) (*mcp.GetPromptResult, error) {
	raw, err := c.Call(ctx, "prompts/get", params)
	if err != nil {
		return nil, err
	}
	var result mcp.GetPromptResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("parse prompts/get: %w", err)
	}
	return &result, nil
}
