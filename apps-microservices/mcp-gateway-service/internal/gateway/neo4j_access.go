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

// neo4jAccessCacheTTL bounds both policy caches (server id → template slug
// and tool prefix, template slug → is-Neo4j). Grants and roles are never cached.
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

// serverAccessKeysLookup is the slice of *repository.ServerRepo the policy
// needs: a server's template_slug and tool_prefix. It returns "", "" and a
// nil error when no mcp_servers row has that id. Needed because the
// in-memory registry does not reliably carry BackendServer.TemplateSlug:
// DiscoverAndRegister only copies it from a previous registry entry, so a
// backend discovered successfully at boot or right after instance creation
// has TemplateSlug == "". The consent screens only hold a server id, so the
// tool_prefix comes from the same row.
type serverAccessKeysLookup interface {
	AccessKeysByID(id string) (templateSlug, toolPrefix string, err error)
}

type serverKeys struct {
	templateSlug string
	toolPrefix   string
}

type cachedKeys struct {
	value   serverKeys
	expires time.Time
}

type cachedBool struct {
	value   bool
	expires time.Time
}

// Neo4jAccess decides service-level access to restricted servers. A backend
// is restricted when its mcp_servers.template_slug names a template whose
// runner is "neo4j", or when its tool_prefix is "hellodata" (the buyer
// export service, docs/superpowers/specs/2026-09-28-mcp-hellodata-server-authorizations-design.md).
// A restricted backend is reachable only by gateway admins and by holders of
// a server_authorizations row for that exact server. A nil *Neo4jAccess
// allows everything.
type Neo4jAccess struct {
	templates templateRunnerLookup
	servers   serverAccessKeysLookup
	users     gatewayUserFinder
	grants    serverAuthorizer
	now       func() time.Time

	mu          sync.Mutex
	serverKeys  map[string]cachedKeys
	slugIsNeo4j map[string]cachedBool
}

// NewNeo4jAccess builds the policy. Any argument may be nil: a nil templates
// lookup makes every templated backend restricted (fail-closed), nil users
// or grants deny every restricted backend, and a nil servers lookup limits
// detection to BackendServer.TemplateSlug.
func NewNeo4jAccess(t templateRunnerLookup, s serverAccessKeysLookup, u gatewayUserFinder, g serverAuthorizer) *Neo4jAccess {
	return &Neo4jAccess{
		templates:   t,
		servers:     s,
		users:       u,
		grants:      g,
		now:         time.Now,
		serverKeys:  make(map[string]cachedKeys),
		slugIsNeo4j: make(map[string]cachedBool),
	}
}

// Restricted reports whether b is a Neo4j template instance or the hellodata
// backend. Lookup errors and a missing template row count as restricted
// (fail-closed).
func (a *Neo4jAccess) Restricted(b *BackendServer) bool {
	if a == nil || b == nil {
		return false
	}
	return a.restricted(b.ID, b.TemplateSlug, b.ToolPrefix)
}

// Allows reports whether the request's end user (the OAuth2 email claim on
// ctx) may reach b. Non-restricted backends are always allowed.
func (a *Neo4jAccess) Allows(ctx context.Context, b *BackendServer) bool {
	if a == nil || b == nil {
		return true
	}
	email, _ := scopetoken.EndUserEmailFromContext(ctx)
	return a.allowsEmail(email, b.ID, b.TemplateSlug, b.ToolPrefix)
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
	return a.allowsEmail(email, serverID, templateSlug, "")
}

// allowsEmail is AllowsEmail with the server's tool_prefix when the caller
// holds it (a registry backend); "" makes the policy resolve it from
// serverID.
func (a *Neo4jAccess) allowsEmail(email, serverID, templateSlug, toolPrefix string) bool {
	if a == nil {
		return true
	}
	if !a.restricted(serverID, templateSlug, toolPrefix) {
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
	keys, _ := a.serverKeysFor(b.ID)
	return keys.templateSlug
}

// restricted: a hellodata prefix (hint or row) restricts at once; otherwise
// a template slug (hint or row) restricts when its runner is Neo4j. A
// template instance is never the hellodata backend, so a non-empty slug hint
// skips the row lookup as before.
func (a *Neo4jAccess) restricted(serverID, slugHint, prefixHint string) bool {
	if prefixHint == hellodataToolPrefix {
		return true
	}
	slug := slugHint
	if slug == "" {
		keys, ok := a.serverKeysFor(serverID)
		if !ok {
			return true
		}
		if keys.toolPrefix == hellodataToolPrefix {
			return true
		}
		slug = keys.templateSlug
	}
	if slug == "" {
		return false
	}
	return a.isNeo4jSlug(slug)
}

// serverKeysFor resolves a server's template slug and tool prefix. ok ==
// false means the lookup failed; the caller must then treat the server as
// restricted.
func (a *Neo4jAccess) serverKeysFor(serverID string) (keys serverKeys, ok bool) {
	if a.servers == nil || serverID == "" {
		return serverKeys{}, true
	}
	now := a.now()
	a.mu.Lock()
	if e, hit := a.serverKeys[serverID]; hit && now.Before(e.expires) {
		a.mu.Unlock()
		return e.value, true
	}
	a.mu.Unlock()

	slug, prefix, err := a.servers.AccessKeysByID(serverID)
	if err != nil {
		log.Printf("[neo4j-access] template_slug/tool_prefix lookup failed for server %s: %v — treating as restricted", serverID, err)
		return serverKeys{}, false
	}
	keys = serverKeys{templateSlug: slug, toolPrefix: prefix}
	a.mu.Lock()
	a.serverKeys[serverID] = cachedKeys{value: keys, expires: now.Add(neo4jAccessCacheTTL)}
	a.mu.Unlock()
	return keys, true
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
