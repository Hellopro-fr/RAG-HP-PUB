package auth

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestAuditMiddleware_PreservesFullBody is the regression for the
// "audit truncated body to 10 KB" bug. Before the fix the middleware
// pre-read up to auditMaxBodyBytes and replaced r.Body with the truncated
// copy, so any handler reading r.Body for a request larger than 10 KB
// silently saw a truncated payload — and the JSON unmarshal exploded
// with "unexpected end of JSON input".
//
// Sends a 32 KB POST through Wrap and asserts the inner handler reads
// the FULL body. The audit channel is left nil — the Wrap path takes
// the `default` branch on send, no panic.
func TestAuditMiddleware_PreservesFullBody(t *testing.T) {
	const bodySize = 32 * 1024
	payload := bytes.Repeat([]byte("A"), bodySize)

	var seen int
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("inner handler read body: %v", err)
		}
		seen = len(got)
		w.WriteHeader(http.StatusOK)
	})

	stub := &AuditMiddleware{ch: nil}
	wrapped := stub.Wrap(inner)

	r := httptest.NewRequest(http.MethodPost, "/api/v1/probe", bytes.NewReader(payload))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	wrapped.ServeHTTP(w, r)

	if seen != bodySize {
		t.Fatalf("inner handler saw %d bytes; want %d (audit middleware truncated)", seen, bodySize)
	}
}

// TestCappedWriter_TruncatesAtMax verifies the helper writer drops bytes
// past `max` while reporting nil error so the upstream TeeReader keeps
// passing data through to the inner handler.
func TestCappedWriter_TruncatesAtMax(t *testing.T) {
	var buf bytes.Buffer
	cw := &cappedWriter{w: &buf, max: 5}
	n, err := cw.Write([]byte("hello world"))
	if err != nil {
		t.Fatalf("Write: %v", err)
	}
	if n != len("hello world") {
		t.Errorf("n=%d want=%d (writer must report full input length so TeeReader stays happy)", n, len("hello world"))
	}
	if buf.String() != "hello" {
		t.Errorf("buf=%q want=%q", buf.String(), "hello")
	}

	// Subsequent writes also no-op once the cap is hit.
	cw.Write([]byte("more"))
	if buf.String() != "hello" {
		t.Errorf("buf after second write=%q want=%q", buf.String(), "hello")
	}
}

// TestSanitizeBody_RedactsSensitiveValues quickly exercises the existing
// sanitizer so the import-doc fix doesn't regress redaction of secrets
// in the audit log.
func TestSanitizeBody_RedactsSensitiveValues(t *testing.T) {
	in := `{"username":"admin","password":"hunter2","token":"abc123"}`
	out := sanitizeBody(in)
	if strings.Contains(out, "hunter2") {
		t.Errorf("password not redacted: %q", out)
	}
	if strings.Contains(out, "abc123") {
		t.Errorf("token not redacted: %q", out)
	}
	if !strings.Contains(out, `"admin"`) {
		t.Errorf("username unexpectedly redacted: %q", out)
	}
}
