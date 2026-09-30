package api

import (
	"crypto/subtle"
	"errors"
	"net/http"
	"net/url"
	"strings"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
)

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

// RunnerEndpoint is one configured template runner. The same AdminToken is
// used in both directions: the gateway sends it to the runner, and the runner
// sends it back on /api/v1/internal/runner/sync, which is how the gateway
// knows which runner is asking.
type RunnerEndpoint struct {
	Client     *runnerclient.Client
	URL        string // in-cluster base URL, e.g. http://mcp-template-neo4j-service:8598
	AdminToken string
}

type runnerNotConfiguredError struct{ name string }

func (e runnerNotConfiguredError) Error() string { return "runner " + e.name + " not configured" }

func isRunnerNotConfigured(err error) bool {
	var e runnerNotConfiguredError
	return errors.As(err, &e)
}

// SetRunners wires the non-Google template runners, keyed by runner name.
// The Google runner passed to NewHandler stays the source for "google".
func (h *Handler) SetRunners(runners map[string]RunnerEndpoint) {
	h.runners = runners
}

func (h *Handler) runnerEndpoint(name string) (RunnerEndpoint, error) {
	if ep, ok := h.runners[name]; ok && ep.Client != nil {
		return ep, nil
	}
	if name == RunnerGoogle && h.runner != nil {
		ep := RunnerEndpoint{Client: h.runner}
		if h.config != nil {
			ep.URL = h.config.GoogleTemplatesRunnerURL
			ep.AdminToken = h.config.GoogleTemplatesRunnerAdminToken
		}
		return ep, nil
	}
	return RunnerEndpoint{}, runnerNotConfiguredError{name: name}
}

func (h *Handler) runnerForTemplate(tpl *db.Template) (RunnerEndpoint, error) {
	return h.runnerEndpoint(templateRunnerName(tpl))
}

// runnerForInstance resolves the runner through the instance's template. A
// missing template row (the FK is RESTRICT, so only in tests or a corrupted
// DB) falls back to the Google runner, the only runner that existed before
// templates.runner.
func (h *Handler) runnerForInstance(inst *db.TemplateInstance) (RunnerEndpoint, error) {
	var tpl *db.Template
	if h.templateRepo != nil && inst != nil {
		if t, err := h.templateRepo.GetBySlug(inst.TemplateSlug); err == nil {
			tpl = t
		}
	}
	return h.runnerForTemplate(tpl)
}

// runnerNameForToken identifies the runner calling the internal sync
// endpoint. Every candidate is compared in constant time. The Google token
// is read from config, not from the client, so the Google runner sync keeps
// working exactly as before when only GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN is set.
func (h *Handler) runnerNameForToken(token string) (string, bool) {
	if token == "" {
		return "", false
	}
	candidates := map[string]string{}
	if h.config != nil && h.config.GoogleTemplatesRunnerAdminToken != "" {
		candidates[RunnerGoogle] = h.config.GoogleTemplatesRunnerAdminToken
	}
	for name, ep := range h.runners {
		if ep.AdminToken != "" {
			candidates[name] = ep.AdminToken
		}
	}
	// A Neo4j token equal to the Google one (app.go then disables the Neo4j
	// runner) means the caller cannot be identified: refuse rather than hand
	// the Google service-account keys to whichever runner asks.
	if h.config != nil && h.config.Neo4jTemplatesRunnerAdminToken != "" &&
		h.config.Neo4jTemplatesRunnerAdminToken == h.config.GoogleTemplatesRunnerAdminToken {
		return "", false
	}
	matched := ""
	for name, expected := range candidates {
		if subtle.ConstantTimeCompare([]byte(token), []byte(expected)) == 1 {
			matched = name
		}
	}
	return matched, matched != ""
}

// runnerHost extracts the host the gateway dials for an instance port. The
// gateway and the runners share a Docker network, so instance URLs are
// http://<runner host>:<instance port>.
func runnerHost(baseURL string) string {
	if u, err := url.Parse(baseURL); err == nil && u.Hostname() != "" {
		return u.Hostname()
	}
	host := strings.TrimPrefix(strings.TrimPrefix(baseURL, "http://"), "https://")
	return strings.SplitN(host, ":", 2)[0]
}

// runnerPrecheckMessage reports whether err is a runner 422 carrying a
// {"detail":{"code","message"}} body (the Neo4j runner's pre-check), and
// returns "<code>: <message>" for the admin.
func runnerPrecheckMessage(err error) (string, bool) {
	var se *runnerclient.StatusError
	if !errors.As(err, &se) || se.StatusCode != http.StatusUnprocessableEntity {
		return "", false
	}
	code, message := se.Detail()
	if code == "" {
		return "", false
	}
	if message == "" {
		return code, true
	}
	return code + ": " + message, true
}
