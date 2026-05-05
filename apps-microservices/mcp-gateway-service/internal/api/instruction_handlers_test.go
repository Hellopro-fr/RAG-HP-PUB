package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/repository"
	"gorm.io/gorm"
)

// withUser returns a copy of req with the auth context set so handlers can
// resolve UserEmailFromContext — mirrors what the auth middleware installs
// at runtime.
func withUser(req *http.Request, email string) *http.Request {
	ctx := context.WithValue(req.Context(), auth.ContextKeyUserEmail, email)
	return req.WithContext(ctx)
}

func newInstructionHandlerTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE llm_instructions (
			id          TEXT PRIMARY KEY,
			title       TEXT NOT NULL,
			body        TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			created_by  TEXT NOT NULL DEFAULT '',
			created_at  datetime,
			updated_at  datetime
		);
		CREATE TABLE llm_instruction_rows (
			id             TEXT PRIMARY KEY,
			instruction_id TEXT NOT NULL,
			kind           TEXT NOT NULL DEFAULT 'per_server',
			title          TEXT NOT NULL DEFAULT '',
			body           TEXT NOT NULL,
			display_order  INTEGER NOT NULL DEFAULT 0,
			created_at     datetime,
			updated_at     datetime
		);
		CREATE TABLE llm_instruction_row_servers (
			row_id    TEXT NOT NULL,
			server_id TEXT NOT NULL,
			PRIMARY KEY (row_id, server_id)
		);
		CREATE TABLE scope_token_instructions (
			token_id       TEXT NOT NULL,
			instruction_id TEXT NOT NULL,
			PRIMARY KEY (token_id, instruction_id)
		);
		CREATE TABLE oauth2_client_instructions (
			client_id      TEXT NOT NULL,
			instruction_id TEXT NOT NULL,
			PRIMARY KEY (client_id, instruction_id)
		);
		CREATE TABLE mcp_servers (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '');`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("ddl: %v", err)
	}
	return gdb
}

func newInstructionHandler(t *testing.T) (*Handler, *gorm.DB) {
	t.Helper()
	gdb := newInstructionHandlerTestDB(t)
	h := &Handler{instructionRepo: repository.NewInstructionRepo(gdb)}
	return h, gdb
}

func seedHandlerServer(t *testing.T, gdb *gorm.DB, id string) {
	t.Helper()
	if err := gdb.Exec("INSERT INTO mcp_servers (id, name) VALUES (?, ?)", id, "s").Error; err != nil {
		t.Fatal(err)
	}
}

func TestHandleInstructions_CreateList(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)

	body, _ := json.Marshal(CreateLLMInstructionRequest{
		Title:       "My page",
		Description: "admin note",
		Rows: []LLMInstructionRowRequest{
			{Title: "Row 1", Body: "Hello body", ServerIDs: []string{s1}},
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/llm-instructions", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.handleLLMInstructions(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("POST status = %d, want 201, body=%s", rr.Code, rr.Body.String())
	}
	var created LLMInstructionResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &created); err != nil {
		t.Fatal(err)
	}
	if created.ID == "" || created.Title != "My page" {
		t.Errorf("unexpected response: %+v", created)
	}
	if len(created.Rows) != 1 || created.Rows[0].Body != "Hello body" {
		t.Errorf("rows not round-tripped: %+v", created.Rows)
	}
	if len(created.Rows[0].ServerIDs) != 1 || created.Rows[0].ServerIDs[0] != s1 {
		t.Errorf("server_ids mismatch: %+v", created.Rows[0].ServerIDs)
	}

	// LIST
	lr := httptest.NewRecorder()
	h.handleLLMInstructions(lr, httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions", nil))
	if lr.Code != http.StatusOK {
		t.Fatalf("LIST status = %d, body=%s", lr.Code, lr.Body.String())
	}
	var list struct {
		Instructions []LLMInstructionResponse `json:"llm_instructions"`
	}
	if err := json.Unmarshal(lr.Body.Bytes(), &list); err != nil {
		t.Fatal(err)
	}
	if len(list.Instructions) != 1 {
		t.Errorf("expected 1 instruction, got %d", len(list.Instructions))
	}
}

func TestHandleInstructions_CreateRejectsMissingFields(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)

	for _, tc := range []struct {
		name string
		body string
	}{
		{"empty title", `{"title":"","rows":[{"body":"b","server_ids":["s"]}]}`},
		{"no rows", `{"title":"t","rows":[]}`},
		{"row empty body", `{"title":"t","rows":[{"body":"","server_ids":["s"]}]}`},
		{"per_server row no servers", `{"title":"t","rows":[{"body":"b"}]}`},
		{"invalid kind", `{"title":"t","rows":[{"kind":"wat","body":"b"}]}`},
		{"invalid json", `not json`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/api/v1/llm-instructions", strings.NewReader(tc.body))
			req.Header.Set("Content-Type", "application/json")
			rr := httptest.NewRecorder()
			h.handleLLMInstructions(rr, req)
			if rr.Code != http.StatusBadRequest {
				t.Errorf("expected 400, got %d, body=%s", rr.Code, rr.Body.String())
			}
		})
	}
}

func TestHandleInstructions_GetUpdateDelete(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	s2 := uuid.New().String()
	for _, s := range []string{s1, s2} {
		seedHandlerServer(t, gdb, s)
	}

	created, err := h.instructionRepo.Create("T", "", []repository.RowInput{
		{Title: "Row", Body: "B", ServerIDs: []string{s1}},
	}, "")
	if err != nil {
		t.Fatal(err)
	}

	// GET
	rr := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+created.ID, nil)
	h.handleLLMInstructionByID(rr, r)
	if rr.Code != http.StatusOK {
		t.Fatalf("GET status = %d, body=%s", rr.Code, rr.Body.String())
	}

	// PUT: title only (rows omitted → preserved)
	newTitle := "NewTitle"
	body, _ := json.Marshal(UpdateLLMInstructionRequest{Title: &newTitle})
	pr := httptest.NewRecorder()
	preq := httptest.NewRequest(http.MethodPut, "/api/v1/llm-instructions/"+created.ID, bytes.NewReader(body))
	preq.Header.Set("Content-Type", "application/json")
	h.handleLLMInstructionByID(pr, preq)
	if pr.Code != http.StatusOK {
		t.Fatalf("PUT status = %d, body=%s", pr.Code, pr.Body.String())
	}
	var updated LLMInstructionResponse
	_ = json.Unmarshal(pr.Body.Bytes(), &updated)
	if updated.Title != "NewTitle" {
		t.Errorf("title should have been updated: %+v", updated)
	}
	if len(updated.Rows) != 1 || updated.Rows[0].Body != "B" {
		t.Errorf("rows should survive title-only update, got %+v", updated.Rows)
	}

	// PUT: replace rows explicitly
	rowsBody := map[string]any{
		"rows": []map[string]any{
			{"title": "Fresh", "body": "new body", "server_ids": []string{s2}},
		},
	}
	raw, _ := json.Marshal(rowsBody)
	pr2 := httptest.NewRecorder()
	preq2 := httptest.NewRequest(http.MethodPut, "/api/v1/llm-instructions/"+created.ID, bytes.NewReader(raw))
	preq2.Header.Set("Content-Type", "application/json")
	h.handleLLMInstructionByID(pr2, preq2)
	if pr2.Code != http.StatusOK {
		t.Fatalf("PUT rows status = %d, body=%s", pr2.Code, pr2.Body.String())
	}
	_ = json.Unmarshal(pr2.Body.Bytes(), &updated)
	if len(updated.Rows) != 1 || updated.Rows[0].Body != "new body" {
		t.Errorf("rows should have been replaced: %+v", updated.Rows)
	}
	if len(updated.Rows[0].ServerIDs) != 1 || updated.Rows[0].ServerIDs[0] != s2 {
		t.Errorf("row server_ids should have been replaced: %+v", updated.Rows[0].ServerIDs)
	}

	// DELETE
	dr := httptest.NewRecorder()
	dreq := httptest.NewRequest(http.MethodDelete, "/api/v1/llm-instructions/"+created.ID, nil)
	h.handleLLMInstructionByID(dr, dreq)
	if dr.Code != http.StatusNoContent {
		t.Fatalf("DELETE status = %d, body=%s", dr.Code, dr.Body.String())
	}

	// GET after DELETE → 404
	rr = httptest.NewRecorder()
	h.handleLLMInstructionByID(rr, httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+created.ID, nil))
	if rr.Code != http.StatusNotFound {
		t.Errorf("expected 404 after delete, got %d", rr.Code)
	}
}

func TestHandleInstructions_ListFilterByServerIDs(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	sA := uuid.New().String()
	sB := uuid.New().String()
	for _, s := range []string{sA, sB} {
		seedHandlerServer(t, gdb, s)
	}
	_, _ = h.instructionRepo.Create("I_A", "", []repository.RowInput{{Body: "a", ServerIDs: []string{sA}}}, "")
	_, _ = h.instructionRepo.Create("I_B", "", []repository.RowInput{{Body: "b", ServerIDs: []string{sB}}}, "")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions?server_ids="+sA, nil)
	rr := httptest.NewRecorder()
	h.handleLLMInstructions(rr, req)
	var resp struct {
		Instructions []LLMInstructionResponse `json:"llm_instructions"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &resp)
	if len(resp.Instructions) != 1 || resp.Instructions[0].Title != "I_A" {
		t.Errorf("filter should return only I_A, got %+v", resp.Instructions)
	}
}

func TestHandleInstructions_CreateGeneralRowNoServersRequired(t *testing.T) {
	h, _ := newInstructionHandler(t)

	body := `{"title":"T","rows":[{"kind":"general","title":"Global","body":"always-injected"}]}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/llm-instructions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.handleLLMInstructions(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("general rows should bypass server-required check, got %d: %s", rr.Code, rr.Body.String())
	}
	var created LLMInstructionResponse
	_ = json.Unmarshal(rr.Body.Bytes(), &created)
	if len(created.Rows) != 1 || created.Rows[0].Kind != "general" {
		t.Errorf("expected 1 general row, got %+v", created.Rows)
	}
	// Stale server_ids must not persist on a general row.
	if len(created.Rows[0].ServerIDs) != 0 {
		t.Errorf("general row should have no server_ids, got %+v", created.Rows[0].ServerIDs)
	}
}

func TestHandleInstructions_GeneralRowDropsStaleServerIDsInput(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)

	body := `{"title":"T","rows":[{"kind":"general","body":"b","server_ids":["` + s1 + `"]}]}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/llm-instructions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.handleLLMInstructions(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("got %d: %s", rr.Code, rr.Body.String())
	}
	var created LLMInstructionResponse
	_ = json.Unmarshal(rr.Body.Bytes(), &created)
	if len(created.Rows[0].ServerIDs) != 0 {
		t.Errorf("general row must ignore server_ids in the request, got %+v", created.Rows[0].ServerIDs)
	}
}

func TestHandleInstructions_OwnershipEnforcement(t *testing.T) {
	// A config-only user must never be able to read, edit or delete another
	// user's page. Owner-less (legacy) pages remain accessible by everyone.
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)

	aliceIns, err := h.instructionRepo.Create(
		"alice page", "", []repository.RowInput{{Body: "a", ServerIDs: []string{s1}}},
		"alice@example.com",
	)
	if err != nil {
		t.Fatal(err)
	}

	intruder := "bob@example.com"

	for _, action := range []struct {
		name    string
		req     *http.Request
		wantStatus int
	}{
		{"GET", withUser(httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+aliceIns.ID, nil), intruder), http.StatusForbidden},
		{"rendered", withUser(httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+aliceIns.ID+"/rendered", nil), intruder), http.StatusForbidden},
		{"usage", withUser(httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+aliceIns.ID+"/usage", nil), intruder), http.StatusForbidden},
		{"delete", withUser(httptest.NewRequest(http.MethodDelete, "/api/v1/llm-instructions/"+aliceIns.ID, nil), intruder), http.StatusForbidden},
	} {
		t.Run("intruder "+action.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			h.handleLLMInstructionByID(rr, action.req)
			if rr.Code != action.wantStatus {
				t.Errorf("got %d, want %d, body=%s", rr.Code, action.wantStatus, rr.Body.String())
			}
		})
	}

	// Owner still gets through.
	rr := httptest.NewRecorder()
	h.handleLLMInstructionByID(
		rr,
		withUser(httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+aliceIns.ID, nil), "alice@example.com"),
	)
	if rr.Code != http.StatusOK {
		t.Errorf("owner should get 200, got %d, body=%s", rr.Code, rr.Body.String())
	}
}

func TestHandleInstructions_ListIsScopedToCaller(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)

	_, _ = h.instructionRepo.Create("alice", "", []repository.RowInput{{Body: "a", ServerIDs: []string{s1}}}, "alice@example.com")
	_, _ = h.instructionRepo.Create("bob", "", []repository.RowInput{{Body: "b", ServerIDs: []string{s1}}}, "bob@example.com")

	rr := httptest.NewRecorder()
	req := withUser(httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions", nil), "bob@example.com")
	h.handleLLMInstructions(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("list status = %d", rr.Code)
	}
	var resp struct {
		Instructions []LLMInstructionResponse `json:"llm_instructions"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &resp)
	if len(resp.Instructions) != 1 || resp.Instructions[0].Title != "bob" {
		t.Errorf("bob should see only his own page, got %+v", resp.Instructions)
	}
}

func TestHandleInstructions_Rendered_ConvertsHtmlBodiesToMarkdown(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)
	created, err := h.instructionRepo.Create("Page", "", []repository.RowInput{
		{
			Kind:      "per_server",
			Title:     "Use search",
			Body:      "<p>Prefer <strong>search_meetings</strong> and see <a href=\"https://x\">docs</a>.</p>",
			ServerIDs: []string{s1},
		},
		{Kind: "general", Body: "<ul><li>alpha</li><li>beta</li></ul>"},
	}, "")
	if err != nil {
		t.Fatal(err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+created.ID+"/rendered", nil)
	rr := httptest.NewRecorder()
	h.handleLLMInstructionByID(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("rendered status = %d, body=%s", rr.Code, rr.Body.String())
	}
	var resp LLMInstructionRenderedResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatal(err)
	}
	md := resp.Markdown
	if strings.Contains(md, "<p>") || strings.Contains(md, "<strong>") || strings.Contains(md, "<li>") {
		t.Errorf("preview must not contain raw HTML tags, got %q", md)
	}
	for _, want := range []string{"## Use search", "**search_meetings**", "[docs](https://x)", "alpha", "beta"} {
		if !strings.Contains(md, want) {
			t.Errorf("expected %q in preview, got %q", want, md)
		}
	}
}

func TestHandleInstructions_Usage(t *testing.T) {
	h, gdb := newInstructionHandler(t)
	s1 := uuid.New().String()
	seedHandlerServer(t, gdb, s1)
	created, _ := h.instructionRepo.Create("T", "", []repository.RowInput{{Body: "B", ServerIDs: []string{s1}}}, "")
	_ = h.instructionRepo.ReplaceTokenInstructions(uuid.New().String(), []string{created.ID})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/llm-instructions/"+created.ID+"/usage", nil)
	rr := httptest.NewRecorder()
	h.handleLLMInstructionByID(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("usage status = %d, body=%s", rr.Code, rr.Body.String())
	}
	var usage LLMInstructionUsageResponse
	_ = json.Unmarshal(rr.Body.Bytes(), &usage)
	if len(usage.TokenIDs) != 1 {
		t.Errorf("expected 1 token, got %+v", usage)
	}
}
