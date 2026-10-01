package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/slack"
)

func TestHandleSlackStatus_Disabled(t *testing.T) {
	h := &Handler{slack: slack.New("", "", "", 0)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/slack/status", nil)
	w := httptest.NewRecorder()
	h.handleSlackStatus(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	var body map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["enabled"] != false {
		t.Errorf("enabled = %v, want false", body["enabled"])
	}
}

func TestHandleSlackStatus_EnabledWithLabel(t *testing.T) {
	h := &Handler{slack: slack.New("http://example.test", "prod", "https://gw", 60)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/slack/status", nil)
	w := httptest.NewRecorder()
	h.handleSlackStatus(w, req)

	var body map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["enabled"] != true {
		t.Errorf("enabled = %v, want true", body["enabled"])
	}
	if body["env_label"] != "prod" {
		t.Errorf("env_label = %v, want prod", body["env_label"])
	}
}

func TestHandleSlackStatus_NilClient(t *testing.T) {
	h := &Handler{slack: nil}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/slack/status", nil)
	w := httptest.NewRecorder()
	h.handleSlackStatus(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	var body map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["enabled"] != false {
		t.Errorf("enabled = %v, want false", body["enabled"])
	}
}

func TestHandleSlackStatus_MethodNotAllowed(t *testing.T) {
	h := &Handler{slack: slack.New("", "", "", 0)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/v1/slack/status", nil)
	w := httptest.NewRecorder()
	h.handleSlackStatus(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want 405", w.Code)
	}
}

func TestHandleSlackTest_Disabled(t *testing.T) {
	h := &Handler{slack: slack.New("", "", "", 0)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/v1/slack/test", nil)
	w := httptest.NewRecorder()
	h.handleSlackTest(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503 (disabled)", w.Code)
	}
}

func TestHandleSlackTest_Success(t *testing.T) {
	var captured []byte
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		captured, _ = io.ReadAll(r.Body)
		w.WriteHeader(200)
	}))
	defer upstream.Close()

	h := &Handler{slack: slack.New(upstream.URL, "staging", "https://gw", 0)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/v1/slack/test", nil)
	w := httptest.NewRecorder()
	h.handleSlackTest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", w.Code, w.Body.String())
	}
	if !strings.Contains(string(captured), "webhook test") {
		t.Fatalf("upstream did not receive test payload: %s", captured)
	}
}

func TestHandleSlackTest_UpstreamFailure(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
	}))
	defer upstream.Close()

	h := &Handler{slack: slack.New(upstream.URL, "", "", 0)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/v1/slack/test", nil)
	w := httptest.NewRecorder()
	h.handleSlackTest(w, req)

	if w.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", w.Code)
	}
}

func TestHandleSlackTest_MethodNotAllowed(t *testing.T) {
	h := &Handler{slack: slack.New("http://example.test", "", "", 0)}
	defer h.slack.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/slack/test", nil)
	w := httptest.NewRecorder()
	h.handleSlackTest(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want 405", w.Code)
	}
}
