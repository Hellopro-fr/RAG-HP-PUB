package ringover

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

// captureServer records the method + path of the last request and replies with
// a fixed JSON body, so we can assert the Empower routes are built correctly.
func captureServer(t *testing.T, body string) (*httptest.Server, *string, *string) {
	t.Helper()
	var gotMethod, gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv, &gotMethod, &gotPath
}

// Empower routes live under /empower/... on the /v2 base (NOT /public/empower)
// and the channel->calluuid conversion is a GET. Verified against the live API
// 2026-06-02: GET /empower/... returns 403 (route exists, Empower subscription
// required) while POST and the /public/ prefix return 404.

func TestGetEmpowerCallUUID_GetsPlatformChannel(t *testing.T) {
	srv, method, path := captureServer(t, `{"calluuid":"abc-123"}`)
	c := NewClient(srv.URL, "key")

	if _, err := c.GetEmpowerCallUUID(context.Background(), "myplatform", "16240763993870283051"); err != nil {
		t.Fatalf("GetEmpowerCallUUID: %v", err)
	}
	if *method != http.MethodGet {
		t.Errorf("method = %s, want GET", *method)
	}
	if want := "/empower/platform/myplatform/channel/16240763993870283051"; *path != want {
		t.Errorf("path = %s, want %s", *path, want)
	}
}

func TestGetCallTranscription_GetsEmpowerCall(t *testing.T) {
	srv, method, path := captureServer(t, `{"call_uuid":"abc-123","transcription":"hi"}`)
	c := NewClient(srv.URL, "key")

	if _, err := c.GetCallTranscription(context.Background(), "abc-123"); err != nil {
		t.Fatalf("GetCallTranscription: %v", err)
	}
	if *method != http.MethodGet {
		t.Errorf("method = %s, want GET", *method)
	}
	if want := "/empower/call/abc-123"; *path != want {
		t.Errorf("path = %s, want %s", *path, want)
	}
}

func TestGetCallSummary_GetsEmpowerCallSummary(t *testing.T) {
	srv, _, path := captureServer(t, `{}`)
	c := NewClient(srv.URL, "key")

	if _, err := c.GetCallSummary(context.Background(), "abc-123"); err != nil {
		t.Fatalf("GetCallSummary: %v", err)
	}
	if want := "/empower/call/abc-123/summary"; *path != want {
		t.Errorf("path = %s, want %s", *path, want)
	}
}

func TestGetTranscriptionByCallID_GetsTranscriptionsCallId(t *testing.T) {
	srv, method, path := captureServer(t, `{"transcription_data":{"speeches":[]}}`)
	c := NewClient(srv.URL, "key")

	if _, err := c.GetTranscriptionByCallID(context.Background(), "10311922507776047602"); err != nil {
		t.Fatalf("GetTranscriptionByCallID: %v", err)
	}
	if *method != http.MethodGet {
		t.Errorf("method = %s, want GET", *method)
	}
	if want := "/transcriptions/10311922507776047602"; *path != want {
		t.Errorf("path = %s, want %s", *path, want)
	}
}

func TestGetCallMoments_GetsEmpowerCallMoments(t *testing.T) {
	srv, _, path := captureServer(t, `{}`)
	c := NewClient(srv.URL, "key")

	if _, err := c.GetCallMoments(context.Background(), "abc-123"); err != nil {
		t.Fatalf("GetCallMoments: %v", err)
	}
	if want := "/empower/call/abc-123/moments"; *path != want {
		t.Errorf("path = %s, want %s", *path, want)
	}
}
