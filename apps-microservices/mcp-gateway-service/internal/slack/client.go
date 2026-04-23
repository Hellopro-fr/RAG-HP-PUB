package slack

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"time"
)

// ErrDisabled is returned by TestWebhook when the client has no webhook URL
// configured. Lets the API layer map this to a 503 with a clear message.
var ErrDisabled = errors.New("slack notifications disabled: SLACK_WEBHOOK_URL not set")

// ClientStatus is the public, non-secret view of the client's configuration.
// Never includes the webhook URL itself.
type ClientStatus struct {
	Enabled  bool
	EnvLabel string
}

const (
	defaultQueueSize   = 64
	defaultHTTPTimeout = 5 * time.Second
	syncPostTimeout    = 2 * time.Second
)

// Client posts notifications to a Slack incoming webhook. Safe for concurrent
// use. When webhookURL is empty the client is a no-op — every Notify /
// NotifySync call returns immediately, which keeps local dev and existing
// deployments (where SLACK_WEBHOOK_URL is unset) working unchanged.
type Client struct {
	webhookURL string
	envLabel   string
	gatewayURL string
	httpClient *http.Client
	queue      chan Event
	limiter    *CooldownLimiter

	closeOnce sync.Once
	done      chan struct{}
}

// New builds a Client. If webhookURL is empty the client is disabled (no-op).
// authCooldownSec controls how often the same (ip, endpoint) can trigger an
// UnauthorizedEvent; <= 0 disables the cooldown (every call allowed).
func New(webhookURL, envLabel, gatewayURL string, authCooldownSec int) *Client {
	c := &Client{
		webhookURL: webhookURL,
		envLabel:   envLabel,
		gatewayURL: gatewayURL,
		httpClient: &http.Client{Timeout: defaultHTTPTimeout},
		limiter:    NewCooldownLimiter(time.Duration(authCooldownSec) * time.Second),
		done:       make(chan struct{}),
	}
	if webhookURL != "" {
		c.queue = make(chan Event, defaultQueueSize)
		go c.worker()
		log.Printf("[slack] notifications enabled (env=%q)", envLabel)
	} else {
		log.Println("[slack] notifications DISABLED (SLACK_WEBHOOK_URL empty)")
	}
	return c
}

// Enabled reports whether the client posts anywhere.
func (c *Client) Enabled() bool { return c != nil && c.webhookURL != "" }

// Status returns a non-secret snapshot of the client's configuration, suitable
// for returning from an admin API endpoint. The webhook URL itself is never
// included.
func (c *Client) Status() ClientStatus {
	if c == nil {
		return ClientStatus{}
	}
	return ClientStatus{
		Enabled:  c.webhookURL != "",
		EnvLabel: c.envLabel,
	}
}

// TestWebhook posts a synchronous test message and returns the delivery
// outcome. Unlike Notify/NotifySync (which swallow errors for best-effort
// operation), this method surfaces the actual error so the API layer can
// report back to the operator who clicked "send test". Returns ErrDisabled
// when the client has no webhook URL.
func (c *Client) TestWebhook(ctx context.Context, triggeredBy string) error {
	if !c.Enabled() {
		return ErrDisabled
	}
	body, err := TestEvent{TriggeredBy: triggeredBy}.ToPayload(c.envLabel, c.gatewayURL)
	if err != nil {
		return fmt.Errorf("build payload: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.webhookURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("post: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return fmt.Errorf("webhook returned %d: %s", resp.StatusCode, truncate(string(respBody), 200))
	}
	return nil
}

// Notify enqueues an event for async delivery. Never blocks the caller — if
// the queue is full the event is dropped and a warning is logged. Hot paths
// (health checker, auth middleware) rely on this to avoid head-of-line blocking.
func (c *Client) Notify(e Event) {
	if !c.Enabled() {
		return
	}
	select {
	case c.queue <- e:
	default:
		log.Printf("[slack] queue full, dropping event of type %T", e)
	}
}

// NotifySync posts synchronously with a short timeout. Used from panic and
// shutdown paths where the worker goroutine may be about to die.
func (c *Client) NotifySync(e Event) {
	if !c.Enabled() {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), syncPostTimeout)
	defer cancel()
	c.postOnce(ctx, e)
}

// AllowAuthAlert reports whether an UnauthorizedEvent for the given
// (ip, endpoint) should fire now, per the configured cooldown. Callers should
// check this before building the event so we avoid both duplicate alerts and
// unnecessary allocations on noisy endpoints.
func (c *Client) AllowAuthAlert(ip, endpoint string) bool {
	if c == nil || c.limiter == nil {
		return true
	}
	return c.limiter.Allow(ip + "|" + endpoint)
}

// Close stops the worker goroutine. Safe to call multiple times and on a nil
// receiver. In-flight events still in the queue are dropped — shutdown is
// best-effort.
func (c *Client) Close() {
	if c == nil {
		return
	}
	c.closeOnce.Do(func() {
		close(c.done)
	})
}

func (c *Client) worker() {
	for {
		select {
		case <-c.done:
			return
		case e := <-c.queue:
			ctx, cancel := context.WithTimeout(context.Background(), defaultHTTPTimeout)
			c.postOnce(ctx, e)
			cancel()
		}
	}
}

func (c *Client) postOnce(ctx context.Context, e Event) {
	body, err := e.ToPayload(c.envLabel, c.gatewayURL)
	if err != nil {
		log.Printf("[slack] failed to build payload: %v", err)
		return
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.webhookURL, bytes.NewReader(body))
	if err != nil {
		log.Printf("[slack] failed to build request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		log.Printf("[slack] POST failed: %v", err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		log.Printf("[slack] POST returned %d: %s", resp.StatusCode, truncate(string(b), 200))
	}
}
