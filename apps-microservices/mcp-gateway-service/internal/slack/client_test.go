package slack

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestClient_DisabledMode_IsNoOp(t *testing.T) {
	c := New("", "prod", "https://gw", 60)
	defer c.Close()

	if c.Enabled() {
		t.Fatal("empty webhook should produce a disabled client")
	}
	// These must not panic and must not block.
	c.Notify(ServerDownEvent{ServerID: "s", ServerName: "n", ServerURL: "u", Err: "e"})
	c.NotifySync(GatewayShutdownEvent{Signal: "SIGTERM"})
}

func TestClient_Notify_PostsToWebhook(t *testing.T) {
	var count int32
	var bodyCopy []byte
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		mu.Lock()
		bodyCopy = b
		mu.Unlock()
		atomic.AddInt32(&count, 1)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	c := New(srv.URL, "prod", "https://gw", 60)
	defer c.Close()

	c.Notify(ServerDownEvent{ServerID: "s", ServerName: "n", ServerURL: "u", Err: "err"})

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) && atomic.LoadInt32(&count) == 0 {
		time.Sleep(10 * time.Millisecond)
	}
	if atomic.LoadInt32(&count) != 1 {
		t.Fatalf("expected 1 POST, got %d", atomic.LoadInt32(&count))
	}
	mu.Lock()
	body := string(bodyCopy)
	mu.Unlock()
	if !strings.Contains(body, "MCP backend DOWN") {
		t.Fatalf("unexpected body: %s", body)
	}
}

func TestClient_NotifySync_BlocksUntilDelivered(t *testing.T) {
	var count int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&count, 1)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	c := New(srv.URL, "", "", 0)
	defer c.Close()
	c.NotifySync(GatewayShutdownEvent{Signal: "SIGTERM"})
	if atomic.LoadInt32(&count) != 1 {
		t.Fatalf("expected 1 POST, got %d", atomic.LoadInt32(&count))
	}
}

func TestClient_ChannelFull_DropsWithoutBlocking(t *testing.T) {
	gate := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-gate
		w.WriteHeader(200)
	}))
	defer srv.Close()
	defer close(gate)

	c := New(srv.URL, "", "", 0)
	defer c.Close()

	done := make(chan struct{})
	go func() {
		for i := 0; i < defaultQueueSize+20; i++ {
			c.Notify(ServerDownEvent{ServerID: fmt.Sprintf("%d", i), ServerName: "n", ServerURL: "u", Err: "e"})
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Fatal("Notify blocked when channel was full")
	}
}

func TestClient_AllowAuthAlert_RespectsCooldown(t *testing.T) {
	c := New("http://unused.invalid", "", "", 60)
	defer c.Close()
	if !c.AllowAuthAlert("1.2.3.4", "/mcp") {
		t.Fatal("first alert should be allowed")
	}
	if c.AllowAuthAlert("1.2.3.4", "/mcp") {
		t.Fatal("second alert within cooldown should be blocked")
	}
	if !c.AllowAuthAlert("5.6.7.8", "/mcp") {
		t.Fatal("different IP should be allowed")
	}
}

func TestClient_AllowAuthAlert_DisabledClient(t *testing.T) {
	// Disabled client still lets limiter decisions through — callers rely on
	// AllowAuthAlert to gate construction regardless of Slack config.
	c := New("", "", "", 60)
	defer c.Close()
	if !c.AllowAuthAlert("1.2.3.4", "/mcp") {
		t.Fatal("first alert should be allowed even when Slack is disabled")
	}
	if c.AllowAuthAlert("1.2.3.4", "/mcp") {
		t.Fatal("second alert within cooldown should be blocked even when Slack is disabled")
	}
}

func TestClient_WebhookError_DoesNotCrash(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
	}))
	defer srv.Close()

	c := New(srv.URL, "", "", 0)
	defer c.Close()
	c.NotifySync(GatewayShutdownEvent{Signal: "SIGTERM"})
}

func TestClient_TestWebhook_Disabled(t *testing.T) {
	c := New("", "", "", 0)
	defer c.Close()
	err := c.TestWebhook(context.Background(), "alice@example.com")
	if err != ErrDisabled {
		t.Fatalf("want ErrDisabled, got %v", err)
	}
}

func TestClient_TestWebhook_Success(t *testing.T) {
	var body []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ = io.ReadAll(r.Body)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	c := New(srv.URL, "prod", "https://gw", 0)
	defer c.Close()
	if err := c.TestWebhook(context.Background(), "alice@example.com"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(string(body), "webhook test") {
		t.Fatalf("unexpected payload: %s", body)
	}
	if !strings.Contains(string(body), "alice@example.com") {
		t.Fatalf("payload missing trigger: %s", body)
	}
}

func TestClient_TestWebhook_Non2xxReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		w.Write([]byte("boom"))
	}))
	defer srv.Close()

	c := New(srv.URL, "", "", 0)
	defer c.Close()
	err := c.TestWebhook(context.Background(), "")
	if err == nil {
		t.Fatal("expected error for 500 response")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Fatalf("error missing status: %v", err)
	}
}

func TestClient_Status(t *testing.T) {
	c := New("http://x", "prod", "https://gw", 60)
	defer c.Close()
	s := c.Status()
	if !s.Enabled {
		t.Error("status.Enabled should be true")
	}
	if s.EnvLabel != "prod" {
		t.Errorf("status.EnvLabel = %q, want %q", s.EnvLabel, "prod")
	}

	var nilClient *Client
	if nilClient.Status().Enabled {
		t.Error("nil client Status.Enabled should be false")
	}

	disabled := New("", "staging", "", 0)
	defer disabled.Close()
	if disabled.Status().Enabled {
		t.Error("disabled Status.Enabled should be false")
	}
	if disabled.Status().EnvLabel != "staging" {
		t.Errorf("disabled Status.EnvLabel = %q", disabled.Status().EnvLabel)
	}
}

func TestClient_CloseIsIdempotent(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
	}))
	defer srv.Close()

	c := New(srv.URL, "", "", 0)
	c.Close()
	c.Close() // must not panic
}
