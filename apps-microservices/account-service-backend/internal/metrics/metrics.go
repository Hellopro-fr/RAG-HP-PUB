package metrics

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	LoginTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_login_total",
		Help: "Login attempts grouped by result.",
	}, []string{"result"})

	TokenIssueTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_token_issue_total",
		Help: "Token issuances grouped by grant type and client.",
	}, []string{"grant_type", "client_id"})

	LogoutWebhookTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_logout_webhook_total",
		Help: "Logout webhook deliveries grouped by status.",
	}, []string{"status"})

	ActiveRefreshTokens = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "account_active_refresh_tokens",
		Help: "Current count of non-revoked, non-expired refresh tokens.",
	})

	TokenReuseAttacks = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "account_token_reuse_attacks_total",
		Help: "Refresh-token reuse attempts grouped by client.",
	}, []string{"client_id"})

	HTTPDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "http_request_duration_seconds",
		Help:    "HTTP request duration histogram.",
		Buckets: prometheus.DefBuckets,
	}, []string{"method", "path", "status"})
)

func Handler() http.Handler {
	return promhttp.Handler()
}
