package auth

import "strings"

// AuthPolicy enumerates the auth modes a service or endpoint may require.
// Mirrors api_catalog.AuthPolicy (proto). The numeric values are independent —
// translation lives in the catalog refresher.
type AuthPolicy int

const (
	PolicyPublic   AuthPolicy = iota
	PolicyBearer
	PolicyAdminKey
)

// ServicePolicy carries the resolved auth state for one service.
type ServicePolicy struct {
	Default      AuthPolicy
	PublicPaths  map[string]struct{} // canonical: leading "/", no trailing "/"
	EndpointAuth map[string]AuthPolicy
}

// AuthSnapshot is the gateway-side view of the catalog's auth state.
// Key is the service name *including* the "-service" suffix.
type AuthSnapshot map[string]ServicePolicy

// canonicalPath turns gin's raw *path param into the storage form used by
// catalog (PublicPaths) and the EndpointAuth keys: "/foo" not "foo" or "foo/".
func canonicalPath(raw string) string {
	return "/" + strings.Trim(raw, "/")
}

// PolicyFor resolves the effective auth policy for a single proxied request.
// Decision order: endpoint override → public_paths bypass → service default → PolicyPublic.
func (s AuthSnapshot) PolicyFor(service, method, path string) AuthPolicy {
	sp, ok := s[service]
	if !ok {
		return PolicyPublic
	}
	cp := canonicalPath(path)
	if p, ok := sp.EndpointAuth[method+" "+cp]; ok {
		return p
	}
	if _, ok := sp.PublicPaths[cp]; ok {
		return PolicyPublic
	}
	return sp.Default
}
