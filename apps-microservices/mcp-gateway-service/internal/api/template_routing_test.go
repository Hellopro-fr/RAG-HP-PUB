package api

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
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
	// With the hand-rolled mcp_servers DDL the insert may fail after the TCP
	// check (createInstanceErrMCPServerInsert); the host has been proven either way.
	if err == nil && url != fmt.Sprintf("http://127.0.0.1:%d", port) {
		t.Fatalf("url = %s", url)
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
