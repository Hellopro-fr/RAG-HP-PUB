package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"mcp-gateway/internal/db"
)

// The instance URL must be built from the selected runner's host: the Neo4j
// runner answers on 127.0.0.1 (a live listener), the Google URL is
// unresolvable. Dialing the Google host would end in createInstanceErrUnhealthy.
func TestCreateInstanceFromSpec_UsesSelectedRunnerHost(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()
	port := ln.Addr().(*net.TCPAddr).Port
	srv := fakeRunner(t, http.StatusOK, fmt.Sprintf(`{"port":%d,"pid":1}`, port))
	h.config.GoogleTemplatesRunnerURL = "http://google-host.invalid:8595"
	withNeo4jRunner(h, srv.URL)
	tpl, err := h.templateRepo.GetBySlug("neo4j")
	if err != nil {
		t.Fatalf("template: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	creds := []byte(`{"uri":"bolt://h:7687","username":"u","password":"p","database":"neo4j"}`)
	_, url, err := h.createInstanceFromSpec(ctx, tpl, "prod", creds, nil, nil, "", "neo4jprod", false, "")
	var cerr *createInstanceError
	if errors.As(err, &cerr) && cerr.Kind == createInstanceErrUnhealthy {
		t.Fatalf("dialed the wrong runner host: %v", err)
	}
	if err != nil {
		t.Fatalf("createInstanceFromSpec: %v", err)
	}
	if want := fmt.Sprintf("http://127.0.0.1:%d", port); url != want {
		t.Fatalf("url = %s, want %s", url, want)
	}
}

func TestHandleCreateInstance_Neo4jRunnerNotConfigured_Returns503(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
		"template_slug": "neo4j",
		"name":          "prod",
	})
	rec := httptest.NewRecorder()
	h.handleCreateInstance(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("got %d body=%s, want 503", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "runner neo4j not configured") {
		t.Errorf("body = %s", rec.Body.String())
	}
}

const precheckAuthFailed = `{"detail":{"code":"neo4j_auth_failed","message":"Neo4j rejected the username or password"}}`

func TestHandleCreateInstance_Neo4jPrecheckFailure_Returns422AndRollsBack(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusUnprocessableEntity, precheckAuthFailed).URL)

	req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
		"template_slug": "neo4j", "name": "prod", "extra_env": `{"NEO4J_READ_ONLY":"true"}`, "tool_prefix": "neo4jprod",
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "wrong",
	})
	rec := httptest.NewRecorder()
	h.handleCreateInstance(rec, req)
	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("got %d body=%s, want 422", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "neo4j_auth_failed: Neo4j rejected the username or password") {
		t.Errorf("body = %s", rec.Body.String())
	}
	var count int64
	gdb.Table("template_instances").Count(&count)
	if count != 0 {
		t.Errorf("template_instances rows = %d, want 0 (rolled back)", count)
	}
}

func TestHandleCreateInstance_Neo4jForbiddenExtraEnv_Returns400(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusOK, `{"port":1,"pid":1}`).URL)
	req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
		"template_slug": "neo4j", "name": "prod", "extra_env": `{"NEO4J_URL":"bolt://evil:7687"}`, "tool_prefix": "neo4jprod",
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "p",
	})
	rec := httptest.NewRecorder()
	h.handleCreateInstance(rec, req)
	if rec.Code != http.StatusBadRequest || !strings.Contains(rec.Body.String(), "NEO4J_URL") {
		t.Fatalf("got %d body=%s, want 400 naming NEO4J_URL", rec.Code, rec.Body.String())
	}
}

func TestHandleCreateInstance_Neo4jRequiresOwnToolPrefix(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusOK, `{"port":1,"pid":1}`).URL)
	for _, prefix := range []string{"", "neo4j", "Neo4j"} {
		req := multipartRequest(t, "/api/v1/template-instances", map[string]string{
			"template_slug": "neo4j", "name": "prod", "tool_prefix": prefix,
			"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "p",
		})
		rec := httptest.NewRecorder()
		h.handleCreateInstance(rec, req)
		if rec.Code != http.StatusBadRequest || !strings.Contains(rec.Body.String(), "tool_prefix") {
			t.Errorf("prefix %q: got %d body=%s, want 400 about tool_prefix", prefix, rec.Code, rec.Body.String())
		}
	}
}

func TestHandleImportTemplates_RunnerChangeWithInstances_Returns409(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	if err := h.instanceRepo.Create(&db.TemplateInstance{ID: "i1", TemplateSlug: "neo4j", Name: "n", CredentialsHash: "h", RunnerStatus: "running", MCPServerID: "i1"}, []byte(`{}`)); err != nil {
		t.Fatalf("seed instance: %v", err)
	}
	// No "runner" in the row: fromTemplateExportRow defaults it to google.
	body := `{"version":1,"templates":[{"slug":"neo4j","name":"Neo4j","stdio_command":"mcp-neo4j-cypher","kind":"stdio","is_active":true}]}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/templates/import", strings.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleImportTemplates(rec, req)
	// Decode first: writeJSON's encoder HTML-escapes '>' as \u003e.
	var errBody ErrorResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &errBody)
	if rec.Code != http.StatusConflict || !strings.Contains(errBody.Error, "cannot change runner neo4j -> google") {
		t.Fatalf("got %d body=%s, want 409", rec.Code, rec.Body.String())
	}
	got, _ := h.templateRepo.GetBySlug("neo4j")
	if got.Runner != RunnerNeo4j {
		t.Errorf("runner changed to %q despite the 409", got.Runner)
	}
}

func TestHandleRotateCredentials_Neo4jPrecheckFailure_KeepsOldCredentials(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	withNeo4jRunner(h, fakeRunner(t, http.StatusUnprocessableEntity, precheckAuthFailed).URL)

	oldCreds := []byte(`{"uri":"bolt://neo4j:7687","username":"reader","password":"good","database":"neo4j"}`)
	sum := sha256.Sum256(oldCreds)
	oldHash := hex.EncodeToString(sum[:])
	oldEnv := json.RawMessage(`{"NEO4J_READ_ONLY":"true"}`)
	inst := &db.TemplateInstance{ID: "inst-1", TemplateSlug: "neo4j", Name: "prod", CredentialsHash: oldHash, ExtraEnv: oldEnv, RunnerStatus: "running", MCPServerID: "inst-1"}
	if err := h.instanceRepo.Create(inst, oldCreds); err != nil {
		t.Fatalf("seed instance: %v", err)
	}

	req := multipartRequest(t, "/api/v1/template-instances/inst-1/rotate-credentials", map[string]string{
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "wrong",
		"extra_env": `{"NEO4J_READ_ONLY":"false"}`,
	})
	rec := httptest.NewRecorder()
	h.handleRotateCredentials(rec, req)
	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("got %d body=%s, want 422", rec.Code, rec.Body.String())
	}
	got, plain, err := h.instanceRepo.GetByIDWithCredentials("inst-1")
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if string(plain) != string(oldCreds) || got.CredentialsHash != oldHash {
		t.Errorf("rejected credentials were persisted: %s / %s", plain, got.CredentialsHash)
	}
	if string(got.ExtraEnv) != string(oldEnv) {
		t.Errorf("rejected extra_env was persisted: %s", got.ExtraEnv)
	}
}
