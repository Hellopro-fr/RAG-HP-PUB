package api

import (
	"context"
	"errors"
	"net/http"
	"time"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/slack"
)

// handleSlackStatus returns the Slack notifications configuration snapshot
// (without the secret webhook URL) so the admin UI can show whether
// notifications are enabled and under which env label.
//
//	GET /api/v1/slack/status
//	Response: { "enabled": bool, "env_label": string }
func (h *Handler) handleSlackStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	s := h.slack.Status()
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"enabled":   s.Enabled,
		"env_label": s.EnvLabel,
	})
}

// handleSlackTest posts a synchronous test message to the configured webhook
// and surfaces the delivery outcome. Gated to admin role via isAdminOnly.
//
//	POST /api/v1/slack/test
//	Response 200: { "status": "ok", "message": "Test message delivered successfully." }
//	Response 503: { "status": "disabled", "message": "Slack notifications are not configured." }
//	Response 502: { "status": "error", "message": "<underlying delivery error>" }
func (h *Handler) handleSlackTest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	// 10 s is well above the client's internal 5 s timeout, so the caller
	// always sees the real delivery outcome rather than a request-side cancel.
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()

	triggeredBy := auth.UserEmailFromContext(r.Context())
	err := h.slack.TestWebhook(ctx, triggeredBy)
	switch {
	case err == nil:
		writeJSON(w, http.StatusOK, map[string]string{
			"status":  "ok",
			"message": "Test message delivered successfully.",
		})
	case errors.Is(err, slack.ErrDisabled):
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"status":  "disabled",
			"message": "Slack notifications are not configured (SLACK_WEBHOOK_URL is empty).",
		})
	default:
		writeJSON(w, http.StatusBadGateway, map[string]string{
			"status":  "error",
			"message": err.Error(),
		})
	}
}
