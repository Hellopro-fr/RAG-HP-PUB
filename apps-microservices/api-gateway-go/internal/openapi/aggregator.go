package openapi

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/errgroup"
)

// AggregateInput holds the base spec and the map of service prefix -> openapi base URL.
type AggregateInput struct {
	Base       map[string]any
	Services   map[string]string
	HTTPClient *http.Client
}

// Aggregate fetches /openapi.json from each service, merges paths under their prefix,
// and resolves schema name collisions by prefixing with a TitleCase service name.
// Non-fatal fetch errors (network, non-200, decode) are silently skipped.
func Aggregate(ctx context.Context, in AggregateInput) (map[string]any, error) {
	if in.HTTPClient == nil {
		in.HTTPClient = &http.Client{Timeout: 5 * time.Second}
	}

	type fetched struct {
		prefix string
		spec   map[string]any
	}
	var (
		mu      sync.Mutex
		results []fetched
	)
	g, gctx := errgroup.WithContext(ctx)
	for prefix, base := range in.Services {
		prefix, base := prefix, base
		g.Go(func() error {
			req, err := http.NewRequestWithContext(gctx, "GET", strings.TrimRight(base, "/")+"/openapi.json", nil)
			if err != nil {
				return nil
			}
			resp, err := in.HTTPClient.Do(req)
			if err != nil {
				return nil
			}
			defer resp.Body.Close()
			if resp.StatusCode != 200 {
				return nil
			}
			var spec map[string]any
			if err := json.NewDecoder(resp.Body).Decode(&spec); err != nil {
				return nil
			}
			mu.Lock()
			results = append(results, fetched{prefix: prefix, spec: spec})
			mu.Unlock()
			return nil
		})
	}
	_ = g.Wait()

	// Pass 1: detect schema name collisions across services.
	tracker := map[string][]string{}
	for _, f := range results {
		comps, _ := f.spec["components"].(map[string]any)
		schemas, _ := comps["schemas"].(map[string]any)
		for name := range schemas {
			tracker[name] = append(tracker[name], f.prefix)
		}
	}
	conflicting := map[string]struct{}{}
	for name, prefixes := range tracker {
		if len(prefixes) > 1 {
			conflicting[name] = struct{}{}
		}
	}

	out := deepCopyMap(in.Base)
	if _, ok := out["paths"]; !ok {
		out["paths"] = map[string]any{}
	}
	if _, ok := out["components"]; !ok {
		out["components"] = map[string]any{}
	}
	outPaths := out["paths"].(map[string]any)
	outComps := out["components"].(map[string]any)
	if _, ok := outComps["schemas"]; !ok {
		outComps["schemas"] = map[string]any{}
	}

	// Pass 2: merge paths and components.
	for _, f := range results {
		schemaPrefix := titlePrefix(f.prefix)
		serviceSnake := prefixToSnake(f.prefix)

		paths, _ := f.spec["paths"].(map[string]any)
		for p, pv := range paths {
			rewritten := prefixRefs(pv, schemaPrefix, conflicting)
			pvm, _ := rewritten.(map[string]any)
			for _, method := range []string{"get", "post", "put", "delete", "patch", "options", "head", "trace"} {
				if op, ok := pvm[method].(map[string]any); ok {
					if id, ok := op["operationId"].(string); ok {
						op["operationId"] = serviceSnake + "_" + id
					}
				}
			}
			outPaths[f.prefix+p] = pvm
		}

		comps, _ := f.spec["components"].(map[string]any)
		for compType, compMap := range comps {
			cm, _ := compMap.(map[string]any)
			outCM, ok := outComps[compType].(map[string]any)
			if !ok {
				outCM = map[string]any{}
				outComps[compType] = outCM
			}
			for k, v := range cm {
				if compType == "schemas" {
					if _, isConflict := conflicting[k]; isConflict {
						outCM[schemaPrefix+k] = prefixRefs(v, schemaPrefix, conflicting)
						continue
					}
				}
				if _, exists := outCM[k]; !exists {
					outCM[k] = v
				}
			}
		}
	}
	return out, nil
}

// deepCopyMap round-trips through JSON for a safe deep copy.
func deepCopyMap(in map[string]any) map[string]any {
	b, _ := json.Marshal(in)
	var out map[string]any
	_ = json.Unmarshal(b, &out)
	return out
}

// titlePrefix converts "/svc-a-service" -> "SvcA" (strips leading slash and "-service" suffix).
func titlePrefix(prefix string) string {
	s := strings.TrimPrefix(prefix, "/")
	s = strings.TrimSuffix(s, "-service")
	parts := strings.Split(s, "-")
	for i, p := range parts {
		if p == "" {
			continue
		}
		parts[i] = strings.ToUpper(p[:1]) + p[1:]
	}
	return strings.Join(parts, "")
}

// prefixToSnake converts "/svc-a-service" -> "svc_a" (for operationId namespacing).
func prefixToSnake(prefix string) string {
	s := strings.TrimPrefix(prefix, "/")
	s = strings.TrimSuffix(s, "-service")
	return strings.ReplaceAll(s, "-", "_")
}

// prefixRefs recursively rewrites $ref values for conflicting schema names.
func prefixRefs(node any, schemaPrefix string, conflicting map[string]struct{}) any {
	switch v := node.(type) {
	case map[string]any:
		out := make(map[string]any, len(v))
		for k, val := range v {
			if k == "$ref" {
				if s, ok := val.(string); ok && strings.Contains(s, "#/components/schemas/") {
					name := s[strings.LastIndex(s, "/")+1:]
					if _, hit := conflicting[name]; hit {
						out[k] = "#/components/schemas/" + schemaPrefix + name
						continue
					}
				}
			}
			out[k] = prefixRefs(val, schemaPrefix, conflicting)
		}
		return out
	case []any:
		out := make([]any, len(v))
		for i, item := range v {
			out[i] = prefixRefs(item, schemaPrefix, conflicting)
		}
		return out
	default:
		return v
	}
}
