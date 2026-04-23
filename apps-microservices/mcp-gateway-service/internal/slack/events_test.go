package slack

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func payloadFor(t *testing.T, e Event, envLabel, gatewayURL string) map[string]any {
	t.Helper()
	raw, err := e.ToPayload(envLabel, gatewayURL)
	if err != nil {
		t.Fatalf("ToPayload error: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("invalid JSON from ToPayload: %v — body: %s", err, raw)
	}
	return m
}

func textOf(t *testing.T, m map[string]any) string {
	t.Helper()
	s, _ := m["text"].(string)
	if s == "" {
		t.Fatalf("payload has no text field: %v", m)
	}
	return s
}

func TestServerDownPayload(t *testing.T) {
	m := payloadFor(t,
		ServerDownEvent{ServerID: "srv-1", ServerName: "my-srv", ServerURL: "http://x", Err: "connection refused"},
		"prod", "https://gw.example",
	)
	text := textOf(t, m)
	for _, want := range []string{"prod", "my-srv", "http://x", "srv-1", "connection refused", "gw.example"} {
		if !strings.Contains(text, want) {
			t.Errorf("text missing %q: %q", want, text)
		}
	}
}

func TestServerUpPayload_WithDownFor(t *testing.T) {
	m := payloadFor(t,
		ServerUpEvent{ServerID: "s", ServerName: "n", ServerURL: "u", DownFor: 2 * time.Minute},
		"", "",
	)
	text := textOf(t, m)
	if !strings.Contains(text, "healthy") {
		t.Errorf("expected 'healthy' in text, got %q", text)
	}
	if !strings.Contains(text, "2m0s") {
		t.Errorf("expected rounded duration in text, got %q", text)
	}
}

func TestServerUpPayload_NoDownFor(t *testing.T) {
	m := payloadFor(t,
		ServerUpEvent{ServerID: "s", ServerName: "n", ServerURL: "u"},
		"", "",
	)
	text := textOf(t, m)
	if strings.Contains(text, "Was unhealthy for") {
		t.Errorf("unexpected downtime line when DownFor=0: %q", text)
	}
}

func TestToolsRegressionPayload(t *testing.T) {
	m := payloadFor(t,
		ToolsRegressionEvent{ServerID: "s", ServerName: "n", PrevCount: 5},
		"", "",
	)
	text := textOf(t, m)
	if !strings.Contains(text, "0 tools") && !strings.Contains(text, "Previous tool count: 5") {
		t.Errorf("text missing regression info: %q", text)
	}
}

func TestUnauthorizedPayload(t *testing.T) {
	m := payloadFor(t,
		UnauthorizedEvent{ClientIP: "1.2.3.4", Endpoint: "/mcp", Reason: "bad token"},
		"", "",
	)
	text := textOf(t, m)
	for _, want := range []string{"1.2.3.4", "/mcp", "bad token"} {
		if !strings.Contains(text, want) {
			t.Errorf("text missing %q: %q", want, text)
		}
	}
}

func TestGatewayShutdownPayload(t *testing.T) {
	m := payloadFor(t, GatewayShutdownEvent{Signal: "SIGTERM"}, "", "")
	text := textOf(t, m)
	if !strings.Contains(text, "SIGTERM") {
		t.Errorf("text missing signal: %q", text)
	}
}

func TestTestEventPayload(t *testing.T) {
	m := payloadFor(t, TestEvent{TriggeredBy: "alice@example.com"}, "staging", "https://gw")
	text := textOf(t, m)
	for _, want := range []string{"staging", "webhook test", "alice@example.com", "gw"} {
		if !strings.Contains(text, want) {
			t.Errorf("text missing %q: %q", want, text)
		}
	}
}

func TestTestEventPayload_NoTriggerWhenEmpty(t *testing.T) {
	m := payloadFor(t, TestEvent{}, "", "")
	text := textOf(t, m)
	if strings.Contains(text, "Triggered by") {
		t.Errorf("expected no 'Triggered by' line when empty, got %q", text)
	}
}

func TestGatewayPanicPayload(t *testing.T) {
	m := payloadFor(t,
		GatewayPanicEvent{Where: "http-server", Err: "boom", Stack: "goroutine 1 ..."},
		"", "",
	)
	text := textOf(t, m)
	for _, want := range []string{"http-server", "boom", "goroutine 1"} {
		if !strings.Contains(text, want) {
			t.Errorf("text missing %q: %q", want, text)
		}
	}
}

func TestTruncate_LargeStackTrimmed(t *testing.T) {
	big := strings.Repeat("a", 5000)
	m := payloadFor(t, GatewayPanicEvent{Where: "x", Err: "e", Stack: big}, "", "")
	text := textOf(t, m)
	if strings.Count(text, "a") > 1500 {
		t.Errorf("stack trace was not truncated, got %d chars", strings.Count(text, "a"))
	}
}

func TestEmptyOptionalFieldsSkipped(t *testing.T) {
	// ServerDown with empty footer (no gatewayURL) must not emit a trailing blank line.
	m := payloadFor(t,
		ServerDownEvent{ServerID: "s", ServerName: "n", ServerURL: "u", Err: "e"},
		"", "",
	)
	text := textOf(t, m)
	if strings.Contains(text, "\n\n") {
		t.Errorf("unexpected blank line in payload: %q", text)
	}
}
