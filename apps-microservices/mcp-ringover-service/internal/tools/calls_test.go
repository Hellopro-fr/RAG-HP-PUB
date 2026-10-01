package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/hellopro/mcp-ringover/internal/ringover"
)

// handleGetCalls, handleListCallsByDate, handleSearchCalls and
// handleGetCallDetails touch the Ringover HTTP client, so full integration
// testing lives in scope_test.go (helpers) and in the docker compose
// integration checks. This file pins the smaller pure-logic helpers used by
// the handlers.

func TestCallTypeForPostCalls(t *testing.T) {
	if got := callTypeForPostCalls(""); got != nil {
		t.Errorf("empty should yield nil, got %v", got)
	}
	got := callTypeForPostCalls("ANSWERED")
	if len(got) != 1 || got[0] != "ANSWERED" {
		t.Errorf("unexpected: %v", got)
	}
}

// captureCallsServer returns Clients wired to a test server that records the
// method, request-URI (path+query) and body of the last request.
func captureCallsServer(t *testing.T) (clients *Clients, method, uri *string, body *[]byte) {
	t.Helper()
	var m, u string
	var b []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		m = r.Method
		u = r.URL.RequestURI()
		b, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"call_list":[]}`))
	}))
	t.Cleanup(srv.Close)
	c := &Clients{Ringover: ringover.NewClient(srv.URL, "key"), DefaultCountryCode: "33"}
	return c, &m, &u, &b
}

func TestHandleSearchCalls_PhoneOnly_PostsAdvancedBothSides(t *testing.T) {
	clients, method, uri, body := captureCallsServer(t)
	if _, err := handleSearchCalls(context.Background(), clients, map[string]any{"phone_number": "611352493"}); err != nil {
		t.Fatal(err)
	}
	if *method != http.MethodPost || *uri != "/calls" {
		t.Fatalf("got %s %s, want POST /calls", *method, *uri)
	}
	var req map[string]any
	if err := json.Unmarshal(*body, &req); err != nil {
		t.Fatalf("body not JSON: %v (%s)", err, *body)
	}
	if req["filter"] != "ADVANCED" {
		t.Errorf("filter = %v, want ADVANCED", req["filter"])
	}
	adv, _ := req["advanced"].(map[string]any)
	if adv == nil {
		t.Fatalf("no advanced object: %s", *body)
	}
	ext, _ := adv["ext_numbers"].([]any)
	intn, _ := adv["int_numbers"].([]any)
	if len(ext) != 1 || len(intn) != 1 {
		t.Fatalf("want ext+int numbers set, got %s", *body)
	}
	if ext[0].(float64) != 33611352493 {
		t.Errorf("ext_numbers[0] = %v, want 33611352493", ext[0])
	}
	if _, has := adv["users"]; has {
		t.Errorf("unexpected users in unscoped request: %s", *body)
	}
}

func TestHandleSearchCalls_PhoneAndScope_CombinesInAdvanced(t *testing.T) {
	clients, method, _, body := captureCallsServer(t)
	ctx := scopedCtx(10, 20)
	if _, err := handleSearchCalls(ctx, clients, map[string]any{"phone_number": "0611352493"}); err != nil {
		t.Fatal(err)
	}
	if *method != http.MethodPost {
		t.Fatalf("method = %s, want POST", *method)
	}
	var req map[string]any
	_ = json.Unmarshal(*body, &req)
	adv := req["advanced"].(map[string]any)
	if users, _ := adv["users"].([]any); len(users) != 2 {
		t.Errorf("want 2 users, got %s", *body)
	}
	if adv["ext_numbers"] == nil {
		t.Errorf("want ext_numbers alongside scope, got %s", *body)
	}
}

func TestHandleSearchCalls_NoPhoneNoScope_UsesGet(t *testing.T) {
	clients, method, uri, _ := captureCallsServer(t)
	if _, err := handleSearchCalls(context.Background(), clients, map[string]any{"call_type": "ANSWERED"}); err != nil {
		t.Fatal(err)
	}
	if *method != http.MethodGet {
		t.Fatalf("method = %s, want GET", *method)
	}
	if !strings.Contains(*uri, "call_type=ANSWERED") {
		t.Errorf("uri = %s, want call_type=ANSWERED", *uri)
	}
}

func TestHandleSearchCalls_UnparseablePhone_NoScope_UsesGet(t *testing.T) {
	clients, method, _, _ := captureCallsServer(t)
	if _, err := handleSearchCalls(context.Background(), clients, map[string]any{"phone_number": "??"}); err != nil {
		t.Fatal(err)
	}
	if *method != http.MethodGet {
		t.Errorf("method = %s, want GET (unparseable phone is ignored)", *method)
	}
}

func TestHandleSearchCalls_ForwardsDatesOnPost(t *testing.T) {
	clients, _, _, body := captureCallsServer(t)
	_, err := handleSearchCalls(context.Background(), clients, map[string]any{
		"phone_number": "611352493", "start_date": "2026-07-01", "end_date": "2026-07-10",
	})
	if err != nil {
		t.Fatal(err)
	}
	var req map[string]any
	_ = json.Unmarshal(*body, &req)
	if req["start_date"] == nil || req["end_date"] == nil {
		t.Errorf("dates not forwarded: %s", *body)
	}
}
