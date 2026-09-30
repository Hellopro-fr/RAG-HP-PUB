package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

func postTemplate(h *Handler, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/templates", strings.NewReader(body))
	rr := httptest.NewRecorder()
	h.handleCreateTemplate(rr, req)
	return rr
}

func TestHandleCreateTemplate_Created(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	body := `{"slug":"neo-x","name":"Neo X","description":"d","icon":"pi pi-x",
		"stdio_command":"mcp-neo4j","stdio_args":["--a","b"],
		"default_env":{"K":"v"},"required_extra_env":[{"name":"N"}],
		"tool_prefix":"neox","tags":["t1"],"kind":"stdio","runner":"neo4j","is_active":true}`
	rr := postTemplate(h, body)
	if rr.Code != http.StatusCreated {
		t.Fatalf("status = %d body=%s", rr.Code, rr.Body.String())
	}
	var got db.Template
	if err := gdb.First(&got, "slug = ?", "neo-x").Error; err != nil {
		t.Fatalf("row not persisted: %v", err)
	}
	if got.Runner != RunnerNeo4j || got.StdioCommand != "mcp-neo4j" || !got.IsActive {
		t.Errorf("unexpected row: %+v", got)
	}
	var resp TemplateResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Slug != "neo-x" || resp.Runner != RunnerNeo4j || resp.InstanceCount != 0 {
		t.Errorf("unexpected response: %+v", resp)
	}
}

func TestHandleCreateTemplate_ExistingSlug_Returns409(t *testing.T) {
	h, gdb := newTemplateAPITestHandler(t)
	seedTemplate(t, gdb, "taken", RunnerGoogle)
	if err := gdb.Exec("INSERT INTO templates (slug, name, stdio_command, is_active) VALUES ('hidden','Hidden','x',0)").Error; err != nil {
		t.Fatalf("seed inactive: %v", err)
	}
	for _, slug := range []string{"taken", "hidden"} {
		rr := postTemplate(h, `{"slug":"`+slug+`","name":"N","stdio_command":"c","is_active":true}`)
		if rr.Code != http.StatusConflict {
			t.Fatalf("%s: status = %d body=%s", slug, rr.Code, rr.Body.String())
		}
		if !strings.Contains(rr.Body.String(), "template slug already used: "+slug) {
			t.Errorf("%s: body = %s", slug, rr.Body.String())
		}
	}
}

func TestHandleCreateTemplate_Validation_Returns400(t *testing.T) {
	cases := map[string]string{
		"missing slug":        `{"name":"N","stdio_command":"c"}`,
		"missing name":        `{"slug":"a","stdio_command":"c"}`,
		"stdio no command":    `{"slug":"a","name":"N","kind":"stdio"}`,
		"default kind no cmd": `{"slug":"a","name":"N"}`,
		"unknown runner":      `{"slug":"a","name":"N","stdio_command":"c","runner":"nope"}`,
		"uppercase slug":      `{"slug":"Ab","name":"N","stdio_command":"c"}`,
		"underscore slug":     `{"slug":"a_b","name":"N","stdio_command":"c"}`,
		"leading dash slug":   `{"slug":"-a","name":"N","stdio_command":"c"}`,
		"slug too long":       `{"slug":"` + strings.Repeat("a", 33) + `","name":"N","stdio_command":"c"}`,
		"reserved export":     `{"slug":"export","name":"N","stdio_command":"c"}`,
		"reserved import":     `{"slug":"import","name":"N","stdio_command":"c"}`,
		"reserved new":        `{"slug":"new","name":"N","stdio_command":"c"}`,
		"invalid json":        `{"slug":`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			h, gdb := newTemplateAPITestHandler(t)
			rr := postTemplate(h, body)
			if rr.Code != http.StatusBadRequest {
				t.Fatalf("status = %d body=%s", rr.Code, rr.Body.String())
			}
			if !strings.Contains(rr.Body.String(), `"error"`) {
				t.Errorf("body lacks error: %s", rr.Body.String())
			}
			var n int64
			gdb.Model(&db.Template{}).Count(&n)
			if n != 0 {
				t.Errorf("row inserted despite 400")
			}
		})
	}
}

func TestIsAdminOnly_TemplatesCreate(t *testing.T) {
	if !isAdminOnly("/api/v1/templates", http.MethodPost) {
		t.Error("POST /api/v1/templates must be admin-only")
	}
	if isAdminOnly("/api/v1/templates", http.MethodGet) {
		t.Error("GET /api/v1/templates must stay open to authenticated users")
	}
}

// Through the real route registration (Register + middleware chain), as admin.
func TestRegister_TemplatesCollection_PostCreatesAndOtherMethods405(t *testing.T) {
	h, _ := newTemplateAPITestHandler(t)
	mux := http.NewServeMux()
	h.Register(mux)
	ctx := context.WithValue(context.Background(), auth.ContextKeyUserRole, auth.RoleAdmin)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/templates",
		strings.NewReader(`{"slug":"via-mux","name":"Via mux","stdio_command":"c","is_active":true}`)).WithContext(ctx)
	rr := httptest.NewRecorder()
	mux.ServeHTTP(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("POST status = %d body=%s", rr.Code, rr.Body.String())
	}

	req = httptest.NewRequest(http.MethodPut, "/api/v1/templates", nil).WithContext(ctx)
	rr = httptest.NewRecorder()
	mux.ServeHTTP(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("PUT status = %d", rr.Code)
	}
	if got := rr.Header().Get("Allow"); got != "GET, POST" {
		t.Errorf("Allow = %q, want %q", got, "GET, POST")
	}
}
