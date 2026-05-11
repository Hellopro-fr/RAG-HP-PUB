// Package datetime provides lenient timestamp parsing matching JS Date.parse
// behaviour, which is what the Express version of the monitor relied on.
//
// The Python crawler stores start_time / end_time in various formats:
//   - "2026-04-29T15:16:20.123456+00:00"    (datetime.now(timezone.utc).isoformat())
//   - "2026-04-29T15:16:20.123456Z"
//   - "2026-04-29T15:16:20.123456"          (datetime.utcnow().isoformat() — naive)
//   - "2026-04-29T15:16:20Z"
//   - 1776924980000                          (raw Unix milliseconds, JSON number)
//
// Go's stdlib parsers are strict, so we try a series of layouts and finally
// fall back to numeric parsing. Returns -1 if nothing matches.
package datetime

import (
	"strconv"
	"strings"
	"time"
)

// layouts is the ordered list of time formats we try, from most specific to
// most permissive. Naive layouts (no timezone) are interpreted as UTC.
var layouts = []string{
	time.RFC3339Nano,
	time.RFC3339,
	"2006-01-02T15:04:05.000000Z07:00",
	"2006-01-02T15:04:05.999999",
	"2006-01-02T15:04:05.000000",
	"2006-01-02T15:04:05Z",
	"2006-01-02T15:04:05",
	"2006-01-02 15:04:05.999999",
	"2006-01-02 15:04:05",
}

// ParseStringMs returns the Unix-millisecond timestamp encoded in s, or -1 on failure.
func ParseStringMs(s string) int64 {
	s = strings.TrimSpace(s)
	if s == "" {
		return -1
	}
	for _, layout := range layouts {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UnixMilli()
		}
	}
	// Last resort: numeric string. Treat values >1e12 as ms, smaller ones as seconds.
	if n, err := strconv.ParseFloat(s, 64); err == nil {
		if n > 1e12 {
			return int64(n)
		}
		if n > 1e9 {
			return int64(n * 1000)
		}
	}
	return -1
}

// ParseAnyMs accepts an interface{} typically pulled from a JSON map and returns
// Unix-ms (-1 on failure). Handles strings, float64 (json.Unmarshal default for
// numbers), and int64.
func ParseAnyMs(v any) int64 {
	switch x := v.(type) {
	case nil:
		return -1
	case string:
		return ParseStringMs(x)
	case float64:
		if x > 1e12 {
			return int64(x)
		}
		if x > 1e9 {
			return int64(x * 1000)
		}
	case int64:
		if x > 1e12 {
			return x
		}
		if x > 1e9 {
			return x * 1000
		}
	case int:
		return ParseAnyMs(int64(x))
	}
	return -1
}

// AnyToISO accepts an interface{} from a JSON map and returns its canonical
// RFC3339Nano string representation, or "" if it cannot be parsed.
// Useful when downstream code expects start_time as a string.
func AnyToISO(v any) string {
	if s, ok := v.(string); ok && s != "" {
		// Already a string; if parseable, normalize, else return as-is.
		if ParseStringMs(s) > 0 {
			return s
		}
		return s
	}
	ms := ParseAnyMs(v)
	if ms <= 0 {
		return ""
	}
	return time.UnixMilli(ms).UTC().Format(time.RFC3339Nano)
}
