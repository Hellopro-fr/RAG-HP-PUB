package httpapi

import (
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/imageproxy"
	mw "github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi/middleware"
	"github.com/go-chi/chi/v5"
)

// roleRateLimiter throttles destructive calls per JWT role (or IP fallback).
// 10/min/role by default — protects against fat-fingered admin loops.
type roleRateLimiter struct {
	mu      sync.Mutex
	calls   map[string][]time.Time
	limit   int
	window  time.Duration
}

func newRoleRateLimiter(limit int, window time.Duration) *roleRateLimiter {
	return &roleRateLimiter{
		calls:  make(map[string][]time.Time),
		limit:  limit,
		window: window,
	}
}

func (l *roleRateLimiter) allow(key string) bool {
	now := time.Now()
	cutoff := now.Add(-l.window)
	l.mu.Lock()
	defer l.mu.Unlock()
	prev := l.calls[key]
	kept := prev[:0]
	for _, t := range prev {
		if t.After(cutoff) {
			kept = append(kept, t)
		}
	}
	if len(kept) >= l.limit {
		l.calls[key] = kept
		return false
	}
	l.calls[key] = append(kept, now)
	return true
}

func keyFromRequest(r *http.Request) string {
	if u := mw.UserFromContext(r.Context()); u != nil {
		if role, _ := u["role"].(string); role != "" {
			return "albums:role:" + role
		}
	}
	return "albums:ip:" + r.RemoteAddr
}

// MountAlbums registers /api/albums/* on the given router.
// The router is expected to already be inside the JWT-protected group.
func MountAlbums(r chi.Router, audit AuditAppender, baseURL string, destructiveLimit int) {
	if destructiveLimit <= 0 {
		destructiveLimit = 10
	}
	limiter := newRoleRateLimiter(destructiveLimit, time.Minute)
	timeout := imageproxy.DefaultTimeout

	fwd := func(method string, pathTemplate string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			path := pathTemplate
			for _, p := range []string{"jobId", "domain", "id", "filename"} {
				if v := chi.URLParam(r, p); v != "" {
					path = strings.ReplaceAll(path, "{"+p+"}", url.PathEscape(v))
				}
			}

			var body io.Reader
			if method == "POST" || method == "PUT" || method == "PATCH" {
				body = r.Body
			}

			res := imageproxy.Forward(r.Context(), r.URL.Query(), body, imageproxy.Options{
				Method:  method,
				Path:    path,
				BaseURL: baseURL,
				Timeout: timeout,
			})
			if res.ContentType != "" {
				w.Header().Set("Content-Type", res.ContentType)
			}
			w.WriteHeader(res.Status)
			if res.Status != 204 && len(res.Body) > 0 {
				_, _ = w.Write(res.Body)
			}
		}
	}

	destructive := func(action string, captureParams []string, method, pathTemplate string) http.HandlerFunc {
		fwdHandler := fwd(method, pathTemplate)
		return func(w http.ResponseWriter, r *http.Request) {
			if !limiter.allow(keyFromRequest(r)) {
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				w.WriteHeader(429)
				_, _ = w.Write([]byte(`{"error":"Too many requests"}`))
				return
			}

			fwdHandler(w, r)

			if audit != nil {
				meta := map[string]any{}
				for _, p := range captureParams {
					if v := chi.URLParam(r, p); v != "" {
						meta[p] = v
					}
				}
				entry := map[string]any{
					"ts":     time.Now().UTC().Format(time.RFC3339Nano),
					"action": action,
					"user":   roleOrAnon(r),
					"status": "ok",
					"target": chi.URLParam(r, "domain"),
				}
				if len(meta) > 0 {
					entry["metadata"] = meta
				}
				_ = audit.Append(r.Context(), entry)
			}
		}
	}

	// GET — read-only, no audit, no per-role rate limit
	r.Get("/", fwd("GET", "/domains/_summary"))
	r.Get("/jobs/{jobId}", fwd("GET", "/jobs/{jobId}"))
	r.Get("/{domain}/errors", fwd("GET", "/sync/{domain}/errors"))
	r.Get("/{domain}/products", fwd("GET", "/domains/{domain}/products"))

	// POST destructive
	r.Post("/{domain}/sync", destructive("sync_album", []string{"domain"}, "POST", "/sync/{domain}"))
	r.Post("/{domain}/products/{id}/redownload", destructive("redownload_product", []string{"domain", "id"}, "POST", "/products/{domain}/{id}/redownload"))
	r.Post("/{domain}/products/{id}/images/{filename}/redownload", destructive("redownload_image", []string{"domain", "id", "filename"}, "POST", "/images/{domain}/{id}/{filename}/redownload"))

	// DELETE destructive
	r.Delete("/{domain}", destructive("delete_album", []string{"domain"}, "DELETE", "/domains/{domain}"))
	r.Delete("/{domain}/products/{id}", destructive("delete_product", []string{"domain", "id"}, "DELETE", "/products/{domain}/{id}"))
	r.Delete("/{domain}/products/{id}/images/{filename}", destructive("delete_image", []string{"domain", "id", "filename"}, "DELETE", "/images/{domain}/{id}/{filename}"))
}

func roleOrAnon(r *http.Request) string {
	if u := mw.UserFromContext(r.Context()); u != nil {
		if role, ok := u["role"].(string); ok && role != "" {
			return role
		}
	}
	return "anonymous"
}

// envIntOr is a utility for callers wiring up the router with env-based config.
func envIntOr(s string, def int) int {
	if s == "" {
		return def
	}
	if n, err := strconv.Atoi(s); err == nil {
		return n
	}
	return def
}
