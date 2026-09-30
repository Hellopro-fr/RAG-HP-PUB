package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCredentialsFromRequest_Neo4jFieldsSerialized(t *testing.T) {
	req := multipartRequest(t, "/x", map[string]string{
		"neo4j_uri": "bolt://neo4j:7687", "neo4j_username": "reader", "neo4j_password": "p w", "neo4j_database": "",
	})
	if err := req.ParseMultipartForm(1 << 20); err != nil {
		t.Fatalf("parse: %v", err)
	}
	got, err := credentialsFromRequest(req, RunnerNeo4j)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	want := `{"uri":"bolt://neo4j:7687","username":"reader","password":"p w","database":"neo4j"}`
	if string(got) != want {
		t.Errorf("got %s, want %s", got, want)
	}
}

func TestCredentialsFromRequest_Neo4jInvalid(t *testing.T) {
	req := multipartRequest(t, "/x", map[string]string{"neo4j_uri": "http://h", "neo4j_username": "u", "neo4j_password": "hunter2"})
	if err := req.ParseMultipartForm(1 << 20); err != nil {
		t.Fatalf("parse: %v", err)
	}
	_, err := credentialsFromRequest(req, RunnerNeo4j)
	if err == nil || !strings.HasPrefix(err.Error(), "invalid credentials: uri scheme") {
		t.Fatalf("err = %v", err)
	}
	if strings.Contains(err.Error(), "hunter2") {
		t.Error("error echoes the password")
	}
}

func TestCredentialsFromRequest_GoogleStillRequiresFile(t *testing.T) {
	req := multipartRequest(t, "/x", map[string]string{"neo4j_uri": "bolt://h", "neo4j_username": "u", "neo4j_password": "p"})
	_, err := credentialsFromRequest(req, RunnerGoogle)
	if err == nil || err.Error() != "missing credentials file" {
		t.Fatalf("err = %v, want missing credentials file", err)
	}
}

func TestValidateRunnerExtraEnv(t *testing.T) {
	for _, env := range []map[string]string{nil, {}, {"NEO4J_READ_ONLY": "true"}, {"NEO4J_READ_ONLY": "false"}} {
		if err := validateRunnerExtraEnv(RunnerNeo4j, env); err != nil {
			t.Errorf("%v: unexpected %v", env, err)
		}
	}
	bad := map[string]map[string]string{
		"NEO4J_URL":       {"NEO4J_URL": "bolt://evil"},
		"NEO4J_TRANSPORT": {"NEO4J_TRANSPORT": "http"},
		"NEO4J_READ_ONLY": {"NEO4J_READ_ONLY": "yes"},
	}
	for want, env := range bad {
		err := validateRunnerExtraEnv(RunnerNeo4j, env)
		if err == nil || !strings.Contains(err.Error(), want) {
			t.Errorf("%v: err = %v", env, err)
		}
	}
	if err := validateRunnerExtraEnv(RunnerGoogle, map[string]string{"GOOGLE_PROJECT_ID": "x"}); err != nil {
		t.Errorf("google must be unrestricted here: %v", err)
	}
}

func TestCredentialsFromRequest_Neo4jIgnoresNonMultipartSources(t *testing.T) {
	body := "neo4j_uri=bolt%3A%2F%2Fh&neo4j_username=u&neo4j_password=p"
	req := httptest.NewRequest(http.MethodPost, "/x?neo4j_uri=bolt://h&neo4j_username=u&neo4j_password=p", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	_, err := credentialsFromRequest(req, RunnerNeo4j)
	if err == nil || err.Error() != "invalid credentials: uri is required" {
		t.Fatalf("err = %v, want invalid credentials: uri is required", err)
	}
}
