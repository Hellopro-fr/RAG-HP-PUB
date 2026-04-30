// Package joblog parses a crawler.log file into a structured payload
// (stats / errors / warnings / rawContent) for /api/jobs/{id}/details.
//
// Mirrors server.js:212-274 (parseLogFile).
package joblog

import (
	"encoding/json"
	"regexp"
	"strings"
)

// Parsed is the structured output of a crawler.log parse.
type Parsed struct {
	Stats      map[string]any `json:"stats"`
	Errors     []string       `json:"errors"`
	Warnings   []string       `json:"warnings"`
	RawContent string         `json:"rawContent"`
	HasStats   bool           `json:"hasStats"`
}

const startMarker = "[stdout] Changed working directory to:"

var (
	statsRegex = regexp.MustCompile(`(?s)\{\s*"CrawlingStats".*?\}\s*\}`)
	errorRegex = regexp.MustCompile(`\[stderr\]\s*ERROR[^\n]*:\s*([^\n]+)`)
	warnRegex  = regexp.MustCompile(`\[stderr\]\s*WARN[^\n]*:\s*([^\n]+)`)
)

// Parse reads a crawler.log content and returns the structured payload.
// Trims the content to keep only the last run when the start marker appears
// multiple times (re-runs). Errors during stats JSON unmarshal are tolerated.
func Parse(content string) Parsed {
	out := Parsed{Errors: []string{}, Warnings: []string{}}

	if last := strings.LastIndex(content, startMarker); last > 0 {
		content = content[last:]
	}
	out.RawContent = content

	if m := statsRegex.FindString(content); m != "" {
		var wrapper struct {
			CrawlingStats map[string]any `json:"CrawlingStats"`
		}
		if err := json.Unmarshal([]byte(m), &wrapper); err == nil && wrapper.CrawlingStats != nil {
			out.Stats = wrapper.CrawlingStats
			out.HasStats = true
		}
	}

	for _, m := range errorRegex.FindAllStringSubmatch(content, -1) {
		out.Errors = append(out.Errors, strings.TrimSpace(m[1]))
	}
	for _, m := range warnRegex.FindAllStringSubmatch(content, -1) {
		out.Warnings = append(out.Warnings, strings.TrimSpace(m[1]))
	}
	return out
}
