package sso

import (
	"context"
	"log"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// userRepo decouples SSOMiddleware from repository.UserRepo for testability.
// Matches auth.UserRepo so the same backing repo serves both modes.
type userRepoIface interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}

// Middleware enforces an authenticated SSO session for all non-public paths.
// On miss it returns 401 (API paths) or 302 → /sso/login (browser paths).
//
// Context keys reuse auth.ContextKey* so downstream handlers don't need to
// know which auth mode is active — auth.UserEmailFromContext etc. work
// regardless.
type Middleware struct {
	client     *Client
	repo       *repository.SSOSessionRepo
	users      userRepoIface
	encryptor  *crypto.Encryptor
	secureCk   bool

	// refreshLocks serializes concurrent refresh attempts per session id.
	// Two requests landing in the refresh window at the same time would each
	// call /token, the second hitting invalid_grant because account-service
	// rotated the refresh token after the first call. We hold a per-sid mutex
	// for the read-decrypt-refresh-write critical section so the second
	// request re-reads the row (now with the rotated tokens) and skips the
	// refresh altogether.
	refreshLocks sync.Map // map[string]*sync.Mutex
}

// NewMiddleware constructs the middleware. Pass nils when wiring up at boot
// before the dependencies are ready (returns a non-nil sentinel for the TDD
// gate test).
func NewMiddleware(client *Client, repo *repository.SSOSessionRepo, users userRepoIface, secureCk bool) *Middleware {
	return &Middleware{client: client, repo: repo, users: users, secureCk: secureCk}
}

// WithEncryptor sets the encryptor used to decrypt access/refresh tokens at
// rest. Required: SSO mode rejects boot without ENCRYPTION_KEY.
func (m *Middleware) WithEncryptor(e *crypto.Encryptor) *Middleware {
	m.encryptor = e
	return m
}

// publicExact + publicPrefixes mirror auth.Middleware exactly so the same
// surface is exempt from auth in both modes.
var publicExact = map[string]bool{
	"/sso/login":    true,
	"/sso/callback": true,
	"/logout":       true,
	"/health":       true,
	"/api/v1/sso/logout":              true,
	"/api/v1/internal/runner/sync":    true,
}

var publicPrefixes = []string{
	"/static",
	"/favicon",
	"/sse",
	"/mcp",
	"/openapi.json",
	"/authorize",
	"/token",
	"/api/v1/oauth2/authorize",
	"/.well-known",
	"/api/v1/public/",
	"/uploads/",
}

// Handler wraps the next http.Handler. Missing dependencies make this a no-op
// (returns next unchanged) so tests using the sentinel Middleware don't crash.
func (m *Middleware) Handler(next http.Handler) http.Handler {
	if m == nil || m.client == nil || m.repo == nil {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path

		if publicExact[path] {
			next.ServeHTTP(w, r)
			return
		}
		for _, prefix := range publicPrefixes {
			if strings.HasPrefix(path, prefix) {
				next.ServeHTTP(w, r)
				return
			}
		}

		sid, err := GetSessionID(r)
		if err != nil {
			m.unauthorized(w, r, "no session")
			return
		}

		sess, err := m.repo.FindByID(sid)
		if err != nil {
			m.unauthorized(w, r, "session not found")
			return
		}

		// Refresh policy: only refresh once the access token is expired (with
		// a 5s slack for clock skew on long-running handlers). Pre-emptive
		// refresh causes invalid_grant races against concurrent requests,
		// since account-service rotates the refresh token on every call.
		// A per-sid mutex serializes refresh attempts; the loser re-reads
		// the now-rotated row and exits the critical section without calling
		// /token a second time.
		if time.Until(sess.AccessExp) < 5*time.Second {
			lockAny, _ := m.refreshLocks.LoadOrStore(sid, &sync.Mutex{})
			lock := lockAny.(*sync.Mutex)
			lock.Lock()
			fresh, err := m.repo.FindByID(sid)
			if err != nil {
				lock.Unlock()
				m.unauthorized(w, r, "session vanished")
				return
			}
			if time.Until(fresh.AccessExp) < 5*time.Second {
				if err := m.refresh(r.Context(), fresh); err != nil {
					lock.Unlock()
					m.refreshLocks.Delete(sid)
					log.Printf("[sso] refresh failed for sid=%s: %v", sid, err)
					_ = m.repo.Delete(sid)
					ClearSessionCookie(w, m.secureCk)
					m.unauthorized(w, r, "refresh failed")
					return
				}
				sess = fresh
			} else {
				sess = fresh
			}
			lock.Unlock()
		}

		_ = m.repo.Touch(sid)

		ctx := r.Context()
		ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, sess.Email)
		ctx = injectName(ctx, m.users, sess.Email)
		ctx = injectRole(ctx, m.users, sess.Email)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (m *Middleware) unauthorized(w http.ResponseWriter, r *http.Request, reason string) {
	if strings.HasPrefix(r.URL.Path, "/api/") {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error":"not authenticated"}`))
		return
	}
	http.Redirect(w, r, "/sso/login?return_to="+url.QueryEscape(r.URL.RequestURI()), http.StatusSeeOther)
}

func (m *Middleware) refresh(ctx context.Context, sess *db.SSOSession) error {
	refreshPlain, err := m.encryptor.Decrypt(sess.RefreshToken)
	if err != nil {
		return err
	}
	tr, err := m.client.Refresh(ctx, string(refreshPlain))
	if err != nil {
		return err
	}
	accessExp := time.Now().Add(time.Duration(tr.ExpiresIn) * time.Second)
	refreshExp := sess.RefreshExp
	if tr.RefreshExpiresIn > 0 {
		refreshExp = time.Now().Add(time.Duration(tr.RefreshExpiresIn) * time.Second)
	}
	accessEnc, err := m.encryptor.Encrypt([]byte(tr.AccessToken))
	if err != nil {
		return err
	}
	refreshEnc, err := m.encryptor.Encrypt([]byte(tr.RefreshToken))
	if err != nil {
		return err
	}
	sess.AccessToken = accessEnc
	sess.RefreshToken = refreshEnc
	sess.AccessExp = accessExp
	sess.RefreshExp = refreshExp
	return m.repo.UpdateTokens(sess.ID, accessEnc, refreshEnc, accessExp, refreshExp)
}

func injectName(ctx context.Context, users userRepoIface, email string) context.Context {
	if users == nil || email == "" {
		return ctx
	}
	u, err := users.GetByEmail(email)
	if err != nil || u == nil {
		return ctx
	}
	return context.WithValue(ctx, auth.ContextKeyUserName, u.DisplayName)
}

func injectRole(ctx context.Context, users userRepoIface, email string) context.Context {
	role := auth.RoleConfigOnly
	if users != nil && email != "" {
		u, err := users.GetByEmail(email)
		if err == nil && u != nil {
			role = u.Role
		}
	}
	return context.WithValue(ctx, auth.ContextKeyUserRole, role)
}
