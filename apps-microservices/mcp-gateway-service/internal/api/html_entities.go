package api

import (
	"encoding/json"
	"html"
)

// Keys in JSON payloads whose string values must NOT be entity-decoded.
// These are machine-readable identifiers (URLs, paths, slugs, CSS classes, code)
// that should be preserved character-for-character.
var skipDecodeKeys = map[string]struct{}{
	"slug":          {},
	"icon":          {},
	"color":         {},
	"src":           {},
	"image":         {},
	"link":          {},
	"url":           {},
	"href":          {},
	"class":         {},
	"cssClass":      {},
	"display_order": {},
	"mcp_config":    {},
	"cli_add_cmd":   {},
	"verify":        {},
	"code":          {},
	"codeField":     {},
}

// decodeEntitiesString applies html.UnescapeString so named (&eacute;) and
// numeric (&#233;) HTML entities become their actual Unicode character.
func decodeEntitiesString(s string) string {
	if s == "" {
		return s
	}
	return html.UnescapeString(s)
}

// decodeEntitiesJSON walks any JSON value (object, array, string, ...) and
// decodes HTML entities in string values, skipping fields listed in
// skipDecodeKeys. Used for persisted JSON fields such as doc_config_guide
// and content arrays from the page builders.
func decodeEntitiesJSON(raw json.RawMessage) json.RawMessage {
	if len(raw) == 0 {
		return raw
	}
	var parsed interface{}
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return raw // leave invalid JSON untouched — let the caller handle the error
	}
	decoded := decodeEntitiesValue("", parsed)
	out, err := json.Marshal(decoded)
	if err != nil {
		return raw
	}
	return out
}

// decodeEntitiesValue recursively traverses a decoded JSON tree and applies
// entity decoding to string leaves that don't live under a skipped key.
func decodeEntitiesValue(key string, v interface{}) interface{} {
	switch val := v.(type) {
	case string:
		if _, skip := skipDecodeKeys[key]; skip {
			return val
		}
		return decodeEntitiesString(val)
	case []interface{}:
		out := make([]interface{}, len(val))
		for i, item := range val {
			out[i] = decodeEntitiesValue(key, item) // arrays inherit the parent key
		}
		return out
	case map[string]interface{}:
		out := make(map[string]interface{}, len(val))
		for k, item := range val {
			out[k] = decodeEntitiesValue(k, item)
		}
		return out
	default:
		return v
	}
}
