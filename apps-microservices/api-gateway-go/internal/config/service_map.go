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

// BuildDownstreamTimeouts returns per-service timeout overrides in seconds.
func BuildDownstreamTimeouts() map[string]float64 {
	return map[string]float64{
		"api-detection-langue-fr-service": 180,
		"extractor-service":               60,
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
