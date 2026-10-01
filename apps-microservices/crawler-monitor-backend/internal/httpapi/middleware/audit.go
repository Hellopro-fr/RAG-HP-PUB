package middleware

import (
	"context"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

type AuditStore interface {
	Append(ctx context.Context, entry map[string]any) error
}

// AuditOptions liste les valeurs de la requete recopiees dans metadata.
// CaptureParams lit les parametres de route chi, CaptureQuery la query string.
type AuditOptions struct {
	CaptureParams []string
	CaptureQuery  []string
}

// StatusRecorder memorise le code HTTP ecrit par le handler amont. Type unique
// partage par l'audit et le proxy albums.
type StatusRecorder struct {
	http.ResponseWriter
	Status int
}

// NewStatusRecorder enveloppe w en supposant un 200 tant que rien n'est ecrit.
func NewStatusRecorder(w http.ResponseWriter) *StatusRecorder {
	return &StatusRecorder{ResponseWriter: w, Status: http.StatusOK}
}

func (s *StatusRecorder) WriteHeader(code int) {
	s.Status = code
	s.ResponseWriter.WriteHeader(code)
}

func AuditMiddleware(store AuditStore, action string, opts AuditOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			sc := NewStatusRecorder(w)
			next.ServeHTTP(sc, r)

			user := "anonymous"
			if u := UserFromContext(r.Context()); u != nil {
				if v, ok := u["role"].(string); ok {
					user = v
				}
			}
			st := "ok"
			if sc.Status >= 400 {
				st = "error"
			}
			entry := map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"user":   user,
				"action": action,
				"status": st,
				"ip":     clientIP(r),
			}
			metadata := map[string]any{}
			for _, k := range opts.CaptureParams {
				if v := chi.URLParam(r, k); v != "" {
					metadata[k] = v
				}
			}
			for _, k := range opts.CaptureQuery {
				if v := r.URL.Query().Get(k); v != "" {
					metadata[k] = v
				}
			}
			// L'identifiant de job est la cible naturelle de l'action : sans
			// lui, l'audit dit "quelqu'un a supprime des queues" sans dire
			// lesquelles.
			if v, ok := metadata["id"]; ok {
				entry["target"] = v
			}
			if len(metadata) > 0 {
				entry["metadata"] = metadata
			}
			_ = store.Append(r.Context(), entry)
		})
	}
}

func clientIP(r *http.Request) string {
	if xf := r.Header.Get("X-Forwarded-For"); xf != "" {
		return xf
	}
	return r.RemoteAddr
}
