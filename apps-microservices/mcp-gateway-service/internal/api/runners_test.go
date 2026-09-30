package api

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"testing"

	"mcp-gateway/internal/config"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
)

func TestTemplateRunnerName(t *testing.T) {
	cases := []struct {
		name string
		tpl  *db.Template
		want string
	}{
		{"nil template", nil, RunnerGoogle},
		{"empty runner", &db.Template{Slug: "ga"}, RunnerGoogle},
		{"neo4j", &db.Template{Slug: "neo4j", Runner: RunnerNeo4j}, RunnerNeo4j},
	}
	for _, c := range cases {
		if got := templateRunnerName(c.tpl); got != c.want {
			t.Errorf("%s: got %q, want %q", c.name, got, c.want)
		}
	}
}

func TestToTemplateResponse_Runner(t *testing.T) {
	if got := toTemplateResponse(db.Template{Slug: "ga"}, 0).Runner; got != RunnerGoogle {
		t.Errorf("legacy row: runner = %q, want google", got)
	}
	if got := toTemplateResponse(db.Template{Slug: "neo4j", Runner: RunnerNeo4j}, 0).Runner; got != RunnerNeo4j {
		t.Errorf("neo4j row: runner = %q", got)
	}
}

func TestTemplateExportRow_RunnerRoundTrip(t *testing.T) {
	row := toTemplateExportRow(db.Template{Slug: "neo4j", Name: "Neo4j", StdioCommand: "mcp-neo4j-cypher", Runner: RunnerNeo4j})
	if row.Runner != RunnerNeo4j {
		t.Fatalf("export runner = %q", row.Runner)
	}
	back, err := fromTemplateExportRow(row)
	if err != nil || back.Runner != RunnerNeo4j {
		t.Fatalf("import: runner=%q err=%v", back.Runner, err)
	}
}

func TestFromTemplateExportRow_RunnerDefaultsAndValidation(t *testing.T) {
	tpl, err := fromTemplateExportRow(TemplateExportRow{Slug: "ga", Name: "GA", StdioCommand: "analytics-mcp"})
	if err != nil || tpl.Runner != RunnerGoogle {
		t.Fatalf("missing runner: got %q err=%v, want google", tpl.Runner, err)
	}
	_, err = fromTemplateExportRow(TemplateExportRow{Slug: "x", Name: "X", StdioCommand: "x", Runner: "docker"})
	if err == nil || !strings.Contains(err.Error(), `unknown runner "docker"`) {
		t.Fatalf("unknown runner: err = %v", err)
	}
}

func TestRunnerEndpoint_Resolution(t *testing.T) {
	google := runnerclient.New("http://mcp-google-templates-runner:8595", "google-tok")
	neo := runnerclient.New("http://mcp-template-neo4j-service:8598", "neo-tok")
	h := &Handler{
		runner: google,
		config: &config.Config{GoogleTemplatesRunnerURL: "http://mcp-google-templates-runner:8595", GoogleTemplatesRunnerAdminToken: "google-tok"},
	}
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: neo, URL: "http://mcp-template-neo4j-service:8598", AdminToken: "neo-tok"}})

	ep, err := h.runnerEndpoint(RunnerGoogle)
	if err != nil || ep.Client != google || ep.URL != "http://mcp-google-templates-runner:8595" {
		t.Fatalf("google: %+v err=%v", ep, err)
	}
	ep, err = h.runnerForTemplate(&db.Template{Slug: "neo4j", Runner: RunnerNeo4j})
	if err != nil || ep.Client != neo {
		t.Fatalf("neo4j: %+v err=%v", ep, err)
	}

	bare := &Handler{}
	_, err = bare.runnerEndpoint(RunnerNeo4j)
	if !isRunnerNotConfigured(err) || err.Error() != "runner neo4j not configured" {
		t.Fatalf("missing neo4j: err=%v", err)
	}
	if _, err := bare.runnerEndpoint(RunnerGoogle); !isRunnerNotConfigured(err) {
		t.Fatalf("missing google: err=%v", err)
	}
}

func TestRunnerNameForToken(t *testing.T) {
	h := &Handler{config: &config.Config{GoogleTemplatesRunnerAdminToken: "google-tok"}}
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: runnerclient.New("http://x:8598", "neo-tok"), URL: "http://x:8598", AdminToken: "neo-tok"}})
	cases := []struct {
		token string
		want  string
		ok    bool
	}{
		{"google-tok", RunnerGoogle, true}, // accepted even without a Google client (previous behaviour)
		{"neo-tok", RunnerNeo4j, true},
		{"wrong", "", false},
		{"", "", false},
	}
	for _, c := range cases {
		got, ok := h.runnerNameForToken(c.token)
		if got != c.want || ok != c.ok {
			t.Errorf("token %q: got (%q,%v), want (%q,%v)", c.token, got, ok, c.want, c.ok)
		}
	}

	// Equal tokens: nobody can be identified, so nobody gets instances.
	same := &Handler{config: &config.Config{GoogleTemplatesRunnerAdminToken: "same", Neo4jTemplatesRunnerAdminToken: "same"}}
	if got, ok := same.runnerNameForToken("same"); ok || got != "" {
		t.Errorf("equal tokens: got (%q,%v), want refusal", got, ok)
	}
}

func TestRunnerHost(t *testing.T) {
	cases := map[string]string{
		"http://mcp-template-neo4j-service:8598":    "mcp-template-neo4j-service",
		"https://mcp-google-templates-runner:8595/": "mcp-google-templates-runner",
		"http://runner": "runner",
		"runner:8598":   "runner",
	}
	for in, want := range cases {
		if got := runnerHost(in); got != want {
			t.Errorf("runnerHost(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestRunnerPrecheckMessage(t *testing.T) {
	pre := &runnerclient.StatusError{StatusCode: http.StatusUnprocessableEntity, Body: map[string]any{
		"detail": map[string]any{"code": "neo4j_auth_failed", "message": "Neo4j rejected the username or password"},
	}}
	if msg, ok := runnerPrecheckMessage(fmt.Errorf("wrapped: %w", pre)); !ok || msg != "neo4j_auth_failed: Neo4j rejected the username or password" {
		t.Errorf("got %q %v", msg, ok)
	}
	if _, ok := runnerPrecheckMessage(&runnerclient.StatusError{StatusCode: http.StatusBadGateway}); ok {
		t.Error("502 must not be a pre-check failure")
	}
	if _, ok := runnerPrecheckMessage(errors.New("dial tcp: refused")); ok {
		t.Error("transport error must not be a pre-check failure")
	}
}

func TestClassifyCreateInstanceError_NewKinds(t *testing.T) {
	status, msg := classifyCreateInstanceError(&createInstanceError{Kind: createInstanceErrRunnerMissing, Err: runnerNotConfiguredError{name: RunnerNeo4j}})
	if status != http.StatusServiceUnavailable || msg != "runner neo4j not configured" {
		t.Errorf("runner missing: %d %q", status, msg)
	}
	pre := &runnerclient.StatusError{StatusCode: 422, Body: map[string]any{"detail": map[string]any{"code": "neo4j_unreachable", "message": "Neo4j unreachable at bolt://x:7687"}}}
	status, msg = classifyCreateInstanceError(&createInstanceError{Kind: createInstanceErrPrecheck, Err: pre})
	if status != http.StatusUnprocessableEntity || msg != "neo4j_unreachable: Neo4j unreachable at bolt://x:7687" {
		t.Errorf("precheck: %d %q", status, msg)
	}
}

func TestRunnerErrorSummary_OmitsBody(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want string
	}{
		{
			"validation 422 echoing the input",
			&runnerclient.StatusError{Method: "POST", Path: "/admin/instances", StatusCode: 422,
				Body: map[string]any{"detail": []any{map[string]any{"input": map[string]any{"credentials_json": "SECRET-CANARY"}}}}},
			"runner POST /admin/instances: status 422",
		},
		{
			"precheck 422",
			&runnerclient.StatusError{Method: "POST", Path: "/admin/instances", StatusCode: 422,
				Body: map[string]any{"detail": map[string]any{"code": "neo4j_auth_failed", "message": "Neo4j rejected the username or password"}}},
			"runner POST /admin/instances: status 422: neo4j_auth_failed",
		},
		{"non-status error", errors.New("dial tcp: refused"), "dial tcp: refused"},
	}
	for _, c := range cases {
		got := runnerErrorSummary(c.err)
		if got != c.want {
			t.Errorf("%s: got %q, want %q", c.name, got, c.want)
		}
		if strings.Contains(got, "SECRET-CANARY") {
			t.Errorf("%s: summary leaks the body: %q", c.name, got)
		}
	}
}
