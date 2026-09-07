package middleware

import (
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/httprate"
)

// LoginRateLimitMax / LoginRateLimitWindow : quota dedie a POST /api/login.
// Le quota global (600 / 15 min) laisse largement la place a un bruteforce du
// mot de passe admin ; la connexion a donc son propre seau, bien plus strict.
const (
	LoginRateLimitMax    = 10
	LoginRateLimitWindow = time.Minute
)

// isTrustedProxyAddr : vrai si l'IP TCP appelante est privee/loopback, donc
// notre reverse proxy nginx sur le reseau docker.
func isTrustedProxyAddr(remoteAddr string) bool {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		host = remoteAddr
	}
	ip := net.ParseIP(strings.TrimSpace(host))
	if ip == nil {
		return false
	}
	return ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast()
}

// keyByTrustedIP choisit la cle du seau : derriere nginx, l'IP TCP est celle du
// proxy et tout le monde partagerait le meme quota, donc on lit
// X-Forwarded-For / X-Real-IP. En acces direct depuis Internet ces en-tetes
// sont forgeables : les honorer offrirait un quota neuf par valeur inventee,
// donc on retombe sur l'IP TCP.
func keyByTrustedIP(r *http.Request) (string, error) {
	if isTrustedProxyAddr(r.RemoteAddr) {
		return httprate.KeyByRealIP(r)
	}
	return httprate.KeyByIP(r)
}

func limitExceeded(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusTooManyRequests)
	_, _ = w.Write([]byte(`{"error":"Too many requests"}`))
}

func RateLimitByIP(max int, window time.Duration) func(http.Handler) http.Handler {
	return httprate.Limit(
		max,
		window,
		httprate.WithKeyFuncs(keyByTrustedIP),
		httprate.WithLimitHandler(limitExceeded),
	)
}

// RateLimitLogin retourne le limiteur dedie a la route de connexion.
func RateLimitLogin() func(http.Handler) http.Handler {
	return RateLimitByIP(LoginRateLimitMax, LoginRateLimitWindow)
}
