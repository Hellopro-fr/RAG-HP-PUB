package api

import "mcp-gateway/internal/db"

// Template runner names (templates.runner). Each runner is a sidecar that
// spawns one mcp-proxy subprocess per template instance.
const (
	RunnerGoogle = "google" // mcp-google-templates-runner
	RunnerNeo4j  = "neo4j"  // mcp-template-neo4j-service
)

var knownRunners = map[string]bool{RunnerGoogle: true, RunnerNeo4j: true}

// templateRunnerName returns the runner owning tpl. Rows created before the
// column existed (and a missing template) belong to the Google runner.
func templateRunnerName(tpl *db.Template) string {
	if tpl == nil || tpl.Runner == "" {
		return RunnerGoogle
	}
	return tpl.Runner
}
