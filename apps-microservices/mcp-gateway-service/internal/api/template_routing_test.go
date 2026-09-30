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

func TestHandleRotateCredentials_Neo4jSuccess_PersistsAfterSpawn(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	var captured map[string]any
	withNeo4jRunner(h, capturingRunner(t, `{"port":15123,"pid":1}`, &captured).URL)

	oldCreds := []byte(`{"uri":"bolt://neo4j:7687","username":"reader","password":"good","database":"neo4j"}`)
	oldSum := sha256.Sum256(oldCreds)
	port := 15123
	inst := &db.TemplateInstance{ID: "inst-1", TemplateSlug: "neo4j", Name: "prod", CredentialsHash: hex.EncodeToString(oldSum[:]),
		ExtraEnv: json.RawMessage(`{"NEO4J_READ_ONLY":"true"}`), RunnerStatus: "running", RunnerPort: &port, MCPServerID: "inst-1"}
	if err := h.instanceRepo.Create(inst, oldCreds); err != nil {
		t.Fatalf("seed instance: %v", err)
	}

	req := multipartRequest(t, "/api/v1/template-instances/inst-1/rotate-credentials", map[string]string{
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "newpw",
		"extra_env": `{"NEO4J_READ_ONLY":"false"}`,
	})
	rec := httptest.NewRecorder()
	h.handleRotateCredentials(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("got %d body=%s, want 202", rec.Code, rec.Body.String())
	}

	newCreds := `{"uri":"bolt://neo4j:7687","username":"reader","password":"newpw","database":"neo4j"}`
	newSum := sha256.Sum256([]byte(newCreds))
	newHash := hex.EncodeToString(newSum[:])
	got, plain, err := h.instanceRepo.GetByIDWithCredentials("inst-1")
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if string(plain) != newCreds || got.CredentialsHash != newHash {
		t.Errorf("new credentials not persisted: %s / %s", plain, got.CredentialsHash)
	}
	if string(got.ExtraEnv) != `{"NEO4J_READ_ONLY":"false"}` {
		t.Errorf("extra_env = %s, want NEO4J_READ_ONLY false", got.ExtraEnv)
	}
	if captured["credentials_hash"] != newHash {
		t.Errorf("spawn credentials_hash = %v, want %s", captured["credentials_hash"], newHash)
	}
	if captured["credentials_json"] != newCreds {
		t.Errorf("spawn credentials_json = %v", captured["credentials_json"])
	}
	if p, _ := captured["runner_port"].(float64); int(p) != 15123 {
		t.Errorf("spawn runner_port = %v, want 15123", captured["runner_port"])
	}
}

func TestHandleImportTemplates_RunnerChangeInactiveTemplate_Returns409(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	if err := gdb.Exec("UPDATE templates SET is_active = 0 WHERE slug = ?", "neo4j").Error; err != nil {
		t.Fatalf("deactivate: %v", err)
	}
	if err := h.instanceRepo.Create(&db.TemplateInstance{ID: "i1", TemplateSlug: "neo4j", Name: "n", CredentialsHash: "h", RunnerStatus: "running", MCPServerID: "i1"}, []byte(`{}`)); err != nil {
		t.Fatalf("seed instance: %v", err)
	}
	body := `{"version":1,"templates":[{"slug":"neo4j","name":"Neo4j","stdio_command":"mcp-neo4j-cypher","kind":"stdio","is_active":true}]}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/templates/import", strings.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleImportTemplates(rec, req)
	var errBody ErrorResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &errBody)
	if rec.Code != http.StatusConflict || !strings.Contains(errBody.Error, "cannot change runner neo4j -> google") {
		t.Fatalf("got %d body=%s, want 409", rec.Code, rec.Body.String())
	}
}

// h.gw and h.registry are nil in the test handler: the post-rotate rediscovery
// is skipped and must never fail the rotate.
func TestHandleRotateCredentials_Neo4jSuccess_NoGateway_StillAccepted(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	var captured map[string]any
	withNeo4jRunner(h, capturingRunner(t, `{"port":15123,"pid":1}`, &captured).URL)
	port := 15123
	inst := &db.TemplateInstance{ID: "inst-1", TemplateSlug: "neo4j", Name: "prod", CredentialsHash: "h",
		ExtraEnv: json.RawMessage(`{"NEO4J_READ_ONLY":"true"}`), RunnerStatus: "running", RunnerPort: &port, MCPServerID: "inst-1"}
	if err := h.instanceRepo.Create(inst, []byte(`{}`)); err != nil {
		t.Fatalf("seed instance: %v", err)
	}
	req := multipartRequest(t, "/api/v1/template-instances/inst-1/rotate-credentials", map[string]string{
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "pw",
		"extra_env": `{"NEO4J_READ_ONLY":"false"}`,
	})
	rec := httptest.NewRecorder()
	h.handleRotateCredentials(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("got %d body=%s, want 202", rec.Code, rec.Body.String())
	}
}

func TestRunnerForInstance_InactiveNeo4jTemplateStillRoutesToNeo4j(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "neo4j", RunnerNeo4j)
	if err := gdb.Model(&db.Template{}).Where("slug = ?", "neo4j").Update("is_active", false).Error; err != nil {
		t.Fatalf("deactivate: %v", err)
	}
	srv := fakeRunner(t, http.StatusOK, `{}`)
	withNeo4jRunner(h, srv.URL)
	ep, err := h.runnerForInstance(&db.TemplateInstance{TemplateSlug: "neo4j"})
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	if ep.URL != srv.URL {
		t.Errorf("ep.URL = %q, want neo4j runner %q", ep.URL, srv.URL)
	}
}
