package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version    string
	Config     *config.Config
	AuditStore AuditAppender
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Get("/health", healthHandler(d.Version))
	if d.Config != nil {
		r.Post("/api/login", loginHandler(d.Config.AdminPasswordHash, d.Config.JWTSecret, d.AuditStore))
	}
	return r
}
