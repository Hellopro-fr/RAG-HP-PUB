package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	mw "github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi/middleware"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version    string
	Config     *config.Config
	RedisStore *redisstore.Client
	FileStore  *filestore.Storage
	AuditStore AuditAppender
}

// auditStoreAdapter adapts *auditstore.Local to AuditAppender.
type auditStoreAdapter struct{ s *auditstore.Local }

func (a *auditStoreAdapter) Append(ctx context.Context, e map[string]any) error {
	return a.s.Append(ctx, e)
}

// WrapAuditStore wraps an *auditstore.Local as an AuditAppender.
func WrapAuditStore(s *auditstore.Local) AuditAppender {
	return &auditStoreAdapter{s: s}
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Use(mw.SecurityHeaders)

	if d.Config != nil && len(d.Config.CorsAllowedOrigins) > 0 {
		r.Use(mw.CORS(d.Config.CorsAllowedOrigins))
	}
	if d.Config != nil && d.Config.RateLimitMax > 0 {
		r.Use(mw.RateLimitByIP(d.Config.RateLimitMax,
			time.Duration(d.Config.RateLimitWindowMs)*time.Millisecond))
	}

	r.Get("/health", healthHandler(d.Version))

	if d.Config != nil {
		r.Post("/api/login", loginHandler(d.Config.AdminPasswordHash, d.Config.JWTSecret, d.AuditStore))
	}

	if d.Config != nil && d.RedisStore != nil {
		r.Group(func(rt chi.Router) {
			rt.Use(mw.JWTAuth(d.Config.JWTSecret))

			rt.Route("/api/jobs", func(rt chi.Router) {
				rt.Get("/", jobsListHandler(d.RedisStore))
				rt.Get("/{id}/details", jobsDetailsHandler(d.RedisStore))
			})

			rt.Get("/api/capacity", capacityGetHandler(d.RedisStore))

			rt.Get("/api/replicas/history", replicasHistoryHandler(d.RedisStore))
			rt.Get("/api/replicas/{id}/history", replicaHistoryByIDHandler(d.RedisStore))

			if d.AuditStore != nil {
				if adapted, ok := d.AuditStore.(*auditStoreAdapter); ok {
					rt.Get("/api/audit", auditListHandler(adapted.s))
				}
			}
		})
	}

	return r
}
