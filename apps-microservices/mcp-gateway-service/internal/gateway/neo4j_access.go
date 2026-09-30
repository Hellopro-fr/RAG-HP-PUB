package gateway

import (
	"context"
	"errors"
	"log"
	"sync"
	"time"

	"gorm.io/gorm"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// neo4jRunner is the templates.runner value of Neo4j templates. Mirrors
// api.RunnerNeo4j — duplicated because internal/api imports this package.
const neo4jRunner = "neo4j"

// neo4jAccessCacheTTL bounds both policy caches (server id → template slug,
// template slug → is-Neo4j). Grants and roles are never cached.
const neo4jAccessCacheTTL = 60 * time.Second

// Neo4jAccessDeniedMessage is the JSON-RPC error message returned when a
// caller without an admin role or a server authorization targets a Neo4j
// template instance.
const Neo4jAccessDeniedMessage = "access denied: this server requires an admin role or a server authorization"

// templateRunnerLookup is the slice of *repository.TemplateRepo the policy
// needs. GetBySlugAny includes inactive templates.
type templateRunnerLookup interface {
	GetBySlugAny(slug string) (*db.Template, error)
}

// serverTemplateSlugLookup is the slice of *repository.ServerRepo the policy
// needs. It returns "" and a nil error when no mcp_servers row has that id.
// Needed because the in-memory registry does not reliably carry
// BackendServer.TemplateSlug: DiscoverAndRegister only copies it from a
// previous registry entry, so a backend discovered successfully at boot or
// right after instance creation has TemplateSlug == "".
type serverTemplateSlugLookup interface {
	TemplateSlugByID(id string) (string, error)
}

type cachedString struct {
	value   string
	expires time.Time
}

type cachedBool struct {
	value   bool
	expires time.Time
}

// Neo4jAccess decides service-level access to Neo4j template instances: a
// backend is restricted when its mcp_servers.template_slug names a template
// whose runner is "neo4j"; a restricted backend is reachable only by gateway
// admins and by holders of a server_authorizations row for that exact
// server. A nil *Neo4jAccess allows everything.
type Neo4jAccess struct {
	templates templateRunnerLookup
	servers   serverTemplateSlugLookup
	users     gatewayUserFinder
	grants    serverAuthorizer
	now       func() time.Time

	mu          sync.Mutex
	serverSlugs map[string]cachedString
	slugIsNeo4j map[string]cachedBool
}

// NewNeo4jAccess builds the policy. Any argument may be nil: a nil templates
// lookup makes every templated backend restricted (fail-closed), nil users
// or grants deny every restricted backend, and a nil servers lookup limits
// detection to BackendServer.TemplateSlug.
func NewNeo4jAccess(t templateRunnerLookup, s serverTemplateSlugLookup, u gatewayUserFinder, g serverAuthorizer) *Neo4jAccess {
	return &Neo4jAccess{
		templates:   t,
		servers:     s,
		users:       u,
		grants:      g,
		now:         time.Now,
		serverSlugs: make(map[string]cachedString),
		slugIsNeo4j: make(map[string]cachedBool),
	}
}

// Restricted reports whether b is a Neo4j template instance. Lookup errors
// and a missing template row count as restricted (fail-closed).
func (a *Neo4jAccess) Restricted(b *BackendServer) bool {
	if a == nil || b == nil {
		return false
	}
	return a.restricted(b.ID, b.TemplateSlug)
}

// Allows reports whether the request's end user (the OAuth2 email claim on
// ctx) may reach b. Non-restricted backends are always allowed.
func (a *Neo4jAccess) Allows(ctx context.Context, b *BackendServer) bool {
	if a == nil || b == nil {
		return true
	}
	email, _ := scopetoken.EndUserEmailFromContext(ctx)
	return a.AllowsEmail(email, b.ID, b.TemplateSlug)
}

// AllowsEmail is Allows for callers that hold the viewer's email directly
// (the OAuth2 consent screens). templateSlug is the server's
// mcp_servers.template_slug when known; "" makes the policy resolve it from
// serverID.
//
// The result is "not restricted OR admin OR grant". The restriction check
// runs first so an unrestricted backend (slug cached) costs no
// gateway_users query. A failed slug / template lookup counts as
// restricted, so an admin still gets through while it fails and every
// other email passes only with a grant on this exact server; callers
// without email are denied.
func (a *Neo4jAccess) AllowsEmail(email, serverID, templateSlug string) bool {
	if a == nil {
		return true
	}
	if !a.restricted(serverID, templateSlug) {
		return true
	}
	if email == "" {
		return false
	}
	if a.isAdmin(email) {
		return true
	}
	if a.grants == nil {
		return false
	}
	return a.grants.IsAuthorized(serverID, email)
}

// DenialSlug returns the template slug to log for a denied call on b.
func (a *Neo4jAccess) DenialSlug(b *BackendServer) string {
	if a == nil || b == nil {
		return ""
	}
	if b.TemplateSlug != "" {
		return b.TemplateSlug
	}
	slug, _ := a.serverSlug(b.ID)
	return slug
}

func (a *Neo4jAccess) restricted(serverID, slugHint string) bool {
	slug := slugHint
	if slug == "" {
		var ok bool
		slug, ok = a.serverSlug(serverID)
		if !ok {
			return true
		}
	}
	if slug == "" {
		return false
	}
	return a.isNeo4jSlug(slug)
}

// serverSlug resolves a server's template slug. ok == false means the lookup
// failed; the caller must then treat the server as restricted.
func (a *Neo4jAccess) serverSlug(serverID string) (slug string, ok bool) {
	if a.servers == nil || serverID == "" {
		return "", true
	}
	now := a.now()
	a.mu.Lock()
	if e, hit := a.serverSlugs[serverID]; hit && now.Before(e.expires) {
		a.mu.Unlock()
		return e.value, true
	}
	a.mu.Unlock()

	slug, err := a.servers.TemplateSlugByID(serverID)
	if err != nil {
		log.Printf("[neo4j-access] template_slug lookup failed for server %s: %v — treating as restricted", serverID, err)
		return "", false
	}
	a.mu.Lock()
	a.serverSlugs[serverID] = cachedString{value: slug, expires: now.Add(neo4jAccessCacheTTL)}
	a.mu.Unlock()
	return slug, true
}

// isNeo4jSlug reports whether the template with this slug runs on the Neo4j
// runner. Unwired lookup, lookup error and missing row all return true. A
// missing row (gorm.ErrRecordNotFound, an orphan template_slug) is a
// definitive answer and is cached like a real one — it can only close
// access — so it is queried and logged once per TTL; other errors are not
// cached.
func (a *Neo4jAccess) isNeo4jSlug(slug string) bool {
	if a.templates == nil {
		return true
	}
	now := a.now()
	a.mu.Lock()
	if e, hit := a.slugIsNeo4j[slug]; hit && now.Before(e.expires) {
		a.mu.Unlock()
		return e.value
	}
	a.mu.Unlock()

	tpl, err := a.templates.GetBySlugAny(slug)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		log.Printf("[neo4j-access] no template row for slug %q — treating as restricted (cached %s)", slug, neo4jAccessCacheTTL)
		a.mu.Lock()
		a.slugIsNeo4j[slug] = cachedBool{value: true, expires: now.Add(neo4jAccessCacheTTL)}
		a.mu.Unlock()
		return true
	}
	if err != nil || tpl == nil {
		log.Printf("[neo4j-access] template lookup failed for slug %q: %v — treating as restricted", slug, err)
		return true
	}
	isNeo4j := tpl.Runner == neo4jRunner
	a.mu.Lock()
	a.slugIsNeo4j[slug] = cachedBool{value: isNeo4j, expires: now.Add(neo4jAccessCacheTTL)}
	a.mu.Unlock()
	return isNeo4j
}

// isAdmin reports whether email is an enabled gateway admin. An admin
// disabled on the Users page (is_allowed = false) is not an admin here, so
// offboarding also closes Neo4j access through still-valid OAuth2 tokens.
func (a *Neo4jAccess) isAdmin(email string) bool {
	if a.users == nil {
		return false
	}
	user, err := a.users.GetByEmail(email)
	if err != nil {
		log.Printf("[neo4j-access] gateway_users lookup failed for %s: %v — not treated as admin", email, err)
		return false
	}
	return user != nil && user.IsAllowed && user.Role == auth.RoleAdmin
}
