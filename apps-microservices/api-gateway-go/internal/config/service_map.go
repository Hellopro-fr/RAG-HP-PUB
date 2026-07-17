package config

import (
	"os"
	"strings"
)

// BuildServiceMap constructs the service routing map from SERVICE_* environment variables.
// Each SERVICE_NAME=url environment variable becomes a route /name-service -> url.
func BuildServiceMap() map[string]string {
	out := map[string]string{}
	for _, kv := range os.Environ() {
		eq := strings.IndexByte(kv, '=')
		if eq <= 0 {
			continue
		}
		k, v := kv[:eq], kv[eq+1:]
		if !strings.HasPrefix(k, "SERVICE_") {
			continue
		}
		name := strings.ToLower(strings.TrimPrefix(k, "SERVICE_"))
		out["/"+name+"-service"] = v
	}
	return out
}

// BuildExcludedRoutes returns the set of routes that should not be proxied to specific services.
// Routes are stored normalized (leading/trailing slashes trimmed).
func BuildExcludedRoutes() map[string][]string {
	raw := map[string][]string{
		"graphdlq-service": {"/dlq/queues"},
	}
	out := make(map[string][]string, len(raw))
	for svc, paths := range raw {
		clean := make([]string, 0, len(paths))
		for _, p := range paths {
			p = strings.Trim(strings.TrimSpace(p), "/")
			if p != "" {
				clean = append(clean, p)
			}
		}
		out[svc] = clean
	}
	return out
}

// BuildDownstreamTimeouts returns per-service timeout overrides in seconds.
func BuildDownstreamTimeouts() map[string]float64 {
	return map[string]float64{
		"api-detection-langue-fr-service": 180,
	}
}

// ExcludedServices returns the set of services that should not be proxied through the gateway.
func ExcludedServices() map[string]struct{} {
	return map[string]struct{}{
		"crawling-service":         {},
		"image_comparator-service": {},
		"graphadmin-service":       {},
	}
}
