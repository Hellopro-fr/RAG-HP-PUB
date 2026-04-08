package transport

import (
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
