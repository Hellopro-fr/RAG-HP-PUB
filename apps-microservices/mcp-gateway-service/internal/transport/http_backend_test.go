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
// instead of JSON-RPC, the error must NOT leak raw markup — it should surface
// the actual page text so the real cause is readable in the result.
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
	if !strings.Contains(msg, "Access Denied") {
		t.Errorf("error should surface the <title>, got: %s", msg)
	}
}

// Real-world Incapsula/Imperva block page: the meaningful text lives in the
// body (no <title>), alongside <script> noise that must not leak.
func TestParseResponseBody_IncapsulaBlockPage(t *testing.T) {
	body := []byte(`<html style="height:100%"><head><META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW"><meta name="format-detection" content="telephone=no"><meta name="viewport" content="initial-scale=1.0"></head><body style="margin:0px;height:100%"><iframe src="/_Incapsula_Resource?..." onload="var i=document.querySelector('iframe')"></iframe>Request unsuccessful. Incapsula incident ID: 1845000900615501534-39445439328884376</body></html>`)
	_, err := parseResponseBody(body)
	if err == nil {
		t.Fatal("expected error for HTML body, got nil")
	}
	msg := err.Error()
	if !strings.Contains(msg, "Request unsuccessful. Incapsula incident ID: 1845000900615501534-39445439328884376") {
		t.Errorf("error should surface the Incapsula incident line, got: %s", msg)
	}
	if strings.Contains(msg, "document.querySelector") || strings.Contains(msg, "<iframe") {
		t.Errorf("error must not contain script/markup noise, got: %s", msg)
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
			name:        "html with title wins",
			body:        `<html><head><title>Bad Gateway</title></head><body>nginx</body></html>`,
			wantContain: []string{"Bad Gateway"},
			wantAbsent:  []string{"<html", "<title", "<body"},
		},
		{
			name:        "html without title falls back to body text",
			body:        `<html><body>  Service   Unavailable  </body></html>`,
			wantContain: []string{"Service Unavailable"},
			wantAbsent:  []string{"<body", "  "},
		},
		{
			name:        "script and style contents are dropped",
			body:        `<html><head><style>.x{color:red}</style><script>alert('xss')</script></head><body>Internal Server Error: SQL syntax error near 'SELEC'</body></html>`,
			wantContain: []string{"Internal Server Error: SQL syntax error near 'SELEC'"},
			wantAbsent:  []string{"alert", "color:red", "<script", "<style"},
		},
		{
			name:        "plain text passthrough collapsed",
			body:        "not   json\n\nat all",
			wantContain: []string{"not json at all"},
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
