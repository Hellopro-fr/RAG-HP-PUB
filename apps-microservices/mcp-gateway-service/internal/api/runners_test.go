package api

import (
	"strings"
	"testing"

	"mcp-gateway/internal/db"
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
