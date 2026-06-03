package transport

import (
	"strings"
	"testing"
)

func TestMaxResponseSizeConstant(t *testing.T) {
	if maxResponseSize != 10*1024*1024 {
		t.Errorf("maxResponseSize should be 10 MB, got %d", maxResponseSize)
	}
}

func TestParseResponseBody_InvalidJSON(t *testing.T) {
	_, err := parseResponseBody([]byte("not json"))
	if err == nil {
		t.Error("expected error for invalid JSON, got nil")
	}
}

func TestParseResponseBody_ValidJSON(t *testing.T) {
	body := []byte(`{"jsonrpc":"2.0","id":1,"result":{"ok":true}}`)
	resp, err := parseResponseBody(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.JSONRPC != "2.0" {
		t.Errorf("expected jsonrpc 2.0, got %s", resp.JSONRPC)
	}
}

func TestParseResponseBody_SSEWrapped(t *testing.T) {
	body := []byte("event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n")
	resp, err := parseResponseBody(body)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.JSONRPC != "2.0" {
		t.Errorf("expected jsonrpc 2.0, got %s", resp.JSONRPC)
	}
}

// When a backend (or a WAF/bot-block proxy fronting it) returns an HTML page
// instead of JSON-RPC, the error must NOT leak raw markup — it should be
// stripped to readable text so the message stays usable in logs and clients.
func TestParseResponseBody_HTMLNotLeakedAsMarkup(t *testing.T) {
	body := []byte(`<html style="height:100%"><head><META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW"><title>Access Denied</title></head><body>Blocked by firewall</body></html>`)
	_, err := parseResponseBody(body)
	if err == nil {
		t.Fatal("expected error for HTML body, got nil")
	}
	msg := err.Error()
	if strings.Contains(msg, "<html") || strings.Contains(msg, "<META") || strings.Contains(msg, "<title>") {
		t.Errorf("error must not contain raw HTML markup, got: %s", msg)
	}
	if !strings.Contains(msg, "HTML page") {
		t.Errorf("error should flag an HTML page, got: %s", msg)
	}
	if !strings.Contains(msg, "Access Denied") {
		t.Errorf("error should surface the <title>, got: %s", msg)
	}
}

func TestSanitizeBodyPreview(t *testing.T) {
	cases := []struct {
		name        string
		body        string
		wantContain []string
		wantAbsent  []string
	}{
		{
			name:        "html with title",
			body:        `<html><head><title>Bad Gateway</title></head><body>nginx</body></html>`,
			wantContain: []string{"HTML page", "Bad Gateway"},
			wantAbsent:  []string{"<html", "<title", "<body"},
		},
		{
			name:        "html without title falls back to text",
			body:        `<html><body>  Service   Unavailable  </body></html>`,
			wantContain: []string{"HTML page", "Service Unavailable"},
			wantAbsent:  []string{"<body", "  "},
		},
		{
			name:        "plain text passthrough collapsed",
			body:        "not   json\n\nat all",
			wantContain: []string{"not json at all"},
			wantAbsent:  []string{"HTML page"},
		},
		{
			name:        "empty body",
			body:        "   ",
			wantContain: []string{"empty"},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := sanitizeBodyPreview([]byte(tc.body))
			for _, want := range tc.wantContain {
				if !strings.Contains(got, want) {
					t.Errorf("expected %q in %q", want, got)
				}
			}
			for _, absent := range tc.wantAbsent {
				if strings.Contains(got, absent) {
					t.Errorf("did not expect %q in %q", absent, got)
				}
			}
		})
	}
}
