package slack

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// Event is any condition worth telling Slack about. ToPayload returns the JSON
// body to POST to the incoming webhook URL.
type Event interface {
	ToPayload(envLabel, gatewayURL string) ([]byte, error)
}

type slackPayload struct {
	Text string `json:"text"`
}

// ServerDownEvent fires when a backend transitions to unhealthy.
type ServerDownEvent struct {
	ServerID   string
	ServerName string
	ServerURL  string
	Err        string
}

func (e ServerDownEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	return buildPayload(
		fmt.Sprintf(":red_circle: %sMCP backend DOWN: *%s*", envPrefix(envLabel), e.ServerName),
		fmt.Sprintf("URL: %s", e.ServerURL),
		fmt.Sprintf("Server ID: `%s`", e.ServerID),
		fmt.Sprintf("Error: `%s`", truncate(e.Err, 400)),
		fmt.Sprintf("Detected at: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// ServerUpEvent fires when a backend recovers.
type ServerUpEvent struct {
	ServerID   string
	ServerName string
	ServerURL  string
	DownFor    time.Duration
}

func (e ServerUpEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	downFor := ""
	if e.DownFor > 0 {
		downFor = fmt.Sprintf("Was unhealthy for: %s", e.DownFor.Round(time.Second))
	}
	return buildPayload(
		fmt.Sprintf(":large_green_circle: %sMCP backend now healthy: *%s*", envPrefix(envLabel), e.ServerName),
		fmt.Sprintf("URL: %s", e.ServerURL),
		fmt.Sprintf("Server ID: `%s`", e.ServerID),
		downFor,
		fmt.Sprintf("Recovered at: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// ToolsRegressionEvent fires when a rediscovery returns 0 tools for a server
// that previously had some.
type ToolsRegressionEvent struct {
	ServerID   string
	ServerName string
	PrevCount  int
}

func (e ToolsRegressionEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	return buildPayload(
		fmt.Sprintf(":warning: %sMCP backend reported 0 tools on rediscovery: *%s*", envPrefix(envLabel), e.ServerName),
		fmt.Sprintf("Previous tool count: %d", e.PrevCount),
		fmt.Sprintf("Server ID: `%s`", e.ServerID),
		fmt.Sprintf("Detected at: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// UnauthorizedEvent fires when an auth-required MCP or /token endpoint rejects
// a request. Caller MUST gate delivery through Client.AllowAuthAlert to avoid
// flooding.
type UnauthorizedEvent struct {
	ClientIP string
	Endpoint string
	Reason   string
}

func (e UnauthorizedEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	return buildPayload(
		fmt.Sprintf(":lock: %sUnauthorized MCP access attempt", envPrefix(envLabel)),
		fmt.Sprintf("Endpoint: `%s`", e.Endpoint),
		fmt.Sprintf("Client IP: `%s`", e.ClientIP),
		fmt.Sprintf("Reason: `%s`", truncate(e.Reason, 200)),
		fmt.Sprintf("Detected at: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// GatewayShutdownEvent fires from main.go during graceful shutdown.
type GatewayShutdownEvent struct {
	Signal string
}

func (e GatewayShutdownEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	return buildPayload(
		fmt.Sprintf(":octagonal_sign: %sMCP gateway shutting down (signal: %s)", envPrefix(envLabel), e.Signal),
		fmt.Sprintf("Timestamp: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// TestEvent is posted from the admin "try webhook" button so an operator can
// confirm their Slack setup works end-to-end without waiting for a real
// incident. Includes the triggering user's email when available.
type TestEvent struct {
	TriggeredBy string
}

func (e TestEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	trigger := ""
	if e.TriggeredBy != "" {
		trigger = fmt.Sprintf("Triggered by: `%s`", e.TriggeredBy)
	}
	return buildPayload(
		fmt.Sprintf(":bell: %sMCP gateway webhook test — if you see this, notifications are working.", envPrefix(envLabel)),
		trigger,
		fmt.Sprintf("Timestamp: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// GatewayPanicEvent is best-effort; posted synchronously from deferred
// recover() before the process exits. The gateway cannot self-report SIGKILL,
// OOM, or hardware failures — pair with an external watcher for those.
type GatewayPanicEvent struct {
	Where string
	Err   interface{}
	Stack string
}

func (e GatewayPanicEvent) ToPayload(envLabel, gatewayURL string) ([]byte, error) {
	return buildPayload(
		fmt.Sprintf(":boom: %sMCP gateway PANIC in %s", envPrefix(envLabel), e.Where),
		fmt.Sprintf("Error: `%v`", e.Err),
		fmt.Sprintf("Stack (truncated):\n```\n%s\n```", truncate(e.Stack, 1200)),
		fmt.Sprintf("Timestamp: %s", nowUTC()),
		gatewayFooter(gatewayURL),
	)
}

// ── helpers ───────────────────────────────────────────────────────────────

func envPrefix(envLabel string) string {
	if envLabel == "" {
		return ""
	}
	return "[" + envLabel + "] "
}

func gatewayFooter(gatewayURL string) string {
	if gatewayURL == "" {
		return ""
	}
	return "Gateway: " + gatewayURL
}

func nowUTC() string {
	return time.Now().UTC().Format(time.RFC3339)
}

// buildPayload joins non-empty lines with \n and marshals as Slack's simplest
// webhook shape (top-level "text"). Empty lines are dropped to avoid blank rows.
func buildPayload(lines ...string) ([]byte, error) {
	out := make([]string, 0, len(lines))
	for _, l := range lines {
		if strings.TrimSpace(l) != "" {
			out = append(out, l)
		}
	}
	return json.Marshal(slackPayload{Text: strings.Join(out, "\n")})
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
