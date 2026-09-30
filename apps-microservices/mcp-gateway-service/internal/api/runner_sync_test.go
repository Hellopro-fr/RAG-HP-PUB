package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
)

func seedInstance(t *testing.T, h *Handler, id, slug string) {
	t.Helper()
	inst := &db.TemplateInstance{ID: id, TemplateSlug: slug, Name: id, CredentialsHash: "h-" + id, RunnerStatus: "running", MCPServerID: id}
	if err := h.instanceRepo.Create(inst, []byte(`{"id":"`+id+`"}`)); err != nil {
		t.Fatalf("seed %s: %v", id, err)
	}
}

func postRunnerSync(h *Handler, token string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/internal/runner/sync", nil)
	if token != "" {
		req.Header.Set("X-Admin-Token", token)
	}
	rec := httptest.NewRecorder()
	h.handleRunnerSync(rec, req)
	return rec
}

func TestHandleRunnerSync_FiltersByRunner(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t) // Google token: google-tok
	h.SetRunners(map[string]RunnerEndpoint{RunnerNeo4j: {Client: runnerclient.New("http://neo:8598", "neo-tok"), URL: "http://neo:8598", AdminToken: "neo-tok"}})
	seedTemplate(t, gdb, "ga", RunnerGoogle)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	seedInstance(t, h, "ga-1", "ga")
	seedInstance(t, h, "neo-1", "neo4j")

	for token, wantID := range map[string]string{"google-tok": "ga-1", "neo-tok": "neo-1"} {
		rec := postRunnerSync(h, token)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s: got %d body=%s", token, rec.Code, rec.Body.String())
		}
		var out struct {
			DesiredInstances []runnerclient.SpawnRequest `json:"desired_instances"`
		}
		if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
			t.Fatalf("decode: %v", err)
		}
		if len(out.DesiredInstances) != 1 || out.DesiredInstances[0].InstanceID != wantID {
			t.Fatalf("%s: got %+v, want only %s", token, out.DesiredInstances, wantID)
		}
		if out.DesiredInstances[0].CredentialsJSON != `{"id":"`+wantID+`"}` {
			t.Errorf("%s: credentials = %s", token, out.DesiredInstances[0].CredentialsJSON)
		}
	}
	for _, token := range []string{"", "wrong"} {
		if rec := postRunnerSync(h, token); rec.Code != http.StatusUnauthorized {
			t.Errorf("token %q: got %d, want 401", token, rec.Code)
		}
	}
}
