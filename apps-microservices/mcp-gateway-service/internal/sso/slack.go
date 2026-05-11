package sso

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

// SSOErrorEvent is the payload the SlackNotifier serialises into a Slack
// incoming-webhook message. Every field is optional except Kind so callers
// can fill in only what is relevant for the error site.
type SSOErrorEvent struct {
	Kind         string // short id: "state_mismatch", "refresh_failed", "token_exchange", "user_blocked", "webhook_signature", ...
	Reason       string // free-form details (error message, mismatch values, etc.)
	UserEmail    string // when known (post token-exchange or post repo lookup)
	Sub          string // account-service `sub` claim, when known
	ClientIP     string // best-effort, may include forwarded chain
	UserAgent    string // browser UA when applicable
	RequestPath  string // r.URL.Path of the failing request
	Query        string // sanitised query (state= / code= shortened)
	ExtraFields  map[string]string // free-form key/value extras
}

// SlackNotifier posts SSO error events to a dedicated Slack incoming webhook
// (LOGIN_SLACK_URL). Designed so login alerts can land in a different
// channel than the operational SLACK_WEBHOOK_URL traffic. When webhookURL
// is empty the notifier is a no-op so production deployments without the
// flag set behave exactly as before.
type SlackNotifier struct {
	webhookURL string
	envLabel   string // optional prefix (e.g. "prod", "staging") shown in the message
	gatewayURL string // included in payload to make multi-deploy alerts disambiguable
	httpClient *http.Client
}

// NewSlackNotifier returns a notifier targeting webhookURL. envLabel and
// gatewayURL are decorative — they help oncall identify which deployment
// emitted the alert. Pass empty strings if not relevant.
func NewSlackNotifier(webhookURL, envLabel, gatewayURL string) *SlackNotifier {
	return &SlackNotifier{
		webhookURL: strings.TrimSpace(webhookURL),
		envLabel:   envLabel,
		gatewayURL: gatewayURL,
		httpClient: &http.Client{Timeout: 5 * time.Second},
	}
}

// Notify posts the event in the background. Non-blocking by design — handler
// hot paths must never wait on Slack delivery. Errors are logged at WARN
// level; the notifier never returns an error to the caller.
func (n *SlackNotifier) Notify(ev SSOErrorEvent) {
	if n == nil || n.webhookURL == "" {
		return
	}
	go n.deliver(ev)
}

func (n *SlackNotifier) deliver(ev SSOErrorEvent) {
	payload := map[string]any{
		"text":        n.formatTitle(ev),
		"attachments": []map[string]any{n.formatAttachment(ev)},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		log.Printf("[sso][slack] marshal failed: %v", err)
		return
	}
	req, err := http.NewRequest(http.MethodPost, n.webhookURL, bytes.NewReader(body))
	if err != nil {
		log.Printf("[sso][slack] build request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := n.httpClient.Do(req)
	if err != nil {
		log.Printf("[sso][slack] post: %v", err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		log.Printf("[sso][slack] webhook returned %d", resp.StatusCode)
	}
}

func (n *SlackNotifier) formatTitle(ev SSOErrorEvent) string {
	parts := []string{"SSO error"}
	if n.envLabel != "" {
		parts = append(parts, "["+n.envLabel+"]")
	}
	if ev.Kind != "" {
		parts = append(parts, ev.Kind)
	}
	return strings.Join(parts, " ")
}

func (n *SlackNotifier) formatAttachment(ev SSOErrorEvent) map[string]any {
	fields := []map[string]any{}
	add := func(k, v string) {
		if v == "" {
			return
		}
		fields = append(fields, map[string]any{"title": k, "value": v, "short": true})
	}
	add("Kind", ev.Kind)
	add("Reason", ev.Reason)
	add("Path", ev.RequestPath)
	add("Query", ev.Query)
	add("User", ev.UserEmail)
	add("Sub", ev.Sub)
	add("Client IP", ev.ClientIP)
	if ev.UserAgent != "" {
		add("User-Agent", truncate(ev.UserAgent, 200))
	}
	add("Gateway", n.gatewayURL)
	add("Env", n.envLabel)
	add("Time", time.Now().UTC().Format(time.RFC3339))
	for k, v := range ev.ExtraFields {
		add(k, v)
	}
	color := "#cc3333"
	return map[string]any{
		"color":  color,
		"text":   fmt.Sprintf("%s — %s", ev.Kind, ev.Reason),
		"fields": fields,
	}
}
