package openapi

import "strings"

const adminSentinel = "\n<!-- ADMIN_SECTION -->"

var httpMethodSet = map[string]struct{}{
	"get": {}, "post": {}, "put": {}, "delete": {}, "patch": {}, "options": {}, "head": {}, "trace": {},
}

func Filter(spec map[string]any) map[string]any {
	out := deepCopyMap(spec)

	if paths, ok := out["paths"].(map[string]any); ok {
		newPaths := map[string]any{}
		for p, pv := range paths {
			pvm, _ := pv.(map[string]any)
			cleaned := map[string]any{}
			anyHTTP := false
			for k, v := range pvm {
				op, ok := v.(map[string]any)
				if !ok {
					cleaned[k] = v
					continue
				}
				if _, isHTTP := httpMethodSet[strings.ToLower(k)]; !isHTTP {
					cleaned[k] = v
					continue
				}
				if isAdminOp(op) {
					continue
				}
				cleaned[k] = v
				anyHTTP = true
			}
			if anyHTTP {
				newPaths[p] = cleaned
			}
		}
		out["paths"] = newPaths
	}

	if comps, ok := out["components"].(map[string]any); ok {
		if schemes, ok := comps["securitySchemes"].(map[string]any); ok {
			delete(schemes, "AdminCle")
		}
	}

	if info, ok := out["info"].(map[string]any); ok {
		if desc, ok := info["description"].(string); ok {
			if idx := strings.Index(desc, adminSentinel); idx >= 0 {
				info["description"] = desc[:idx]
			}
		}
	}
	return out
}

func isAdminOp(op map[string]any) bool {
	sec, _ := op["security"].([]any)
	for _, s := range sec {
		m, _ := s.(map[string]any)
		if _, hit := m["AdminCle"]; hit {
			return true
		}
	}
	return false
}
