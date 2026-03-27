package auth

import (
	"log"
	"net/http"
	"strings"
)

// Config holds JWT/auth configuration.
type Config struct {
	JWTSecret   string
	JWTAlgo     string // always HS256
	JWTAudience string
	AuthURL     string // hellopro.fr auth endpoint
	Enabled     bool
}

// publicPaths that don't require authentication.
var publicExact = map[string]bool{
	"/login":  true,
	"/logout": true,
	"/health": true,
}

var publicPrefixes = []string{
	"/static",
	"/favicon",
	"/sse",    // MCP SSE transport (machine-to-machine)
	"/mcp",    // MCP streamable HTTP transport (machine-to-machine)
	"/openapi.json",
}

// Middleware returns an HTTP middleware that enforces authentication.
func Middleware(cfg Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		if !cfg.Enabled {
			return next
		}
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			path := r.URL.Path

			// Public exact match
			if publicExact[path] {
				next.ServeHTTP(w, r)
				return
			}

			// Public prefix match
			for _, prefix := range publicPrefixes {
				if strings.HasPrefix(path, prefix) {
					next.ServeHTTP(w, r)
					return
				}
			}

			// Check session
			session, err := GetSession(r, cfg.JWTSecret)
			if err != nil {
				log.Printf("[auth] no valid session for %s: %v", path, err)
				http.Redirect(w, r, "/login", http.StatusSeeOther)
				return
			}

			// Validate JWT token in session
			_, err = ValidateJWT(session.Token, cfg.JWTSecret, cfg.JWTAudience)
			if err != nil {
				log.Printf("[auth] invalid token for %s: %v", path, err)
				ClearSession(w)
				http.Redirect(w, r, "/login", http.StatusSeeOther)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}