package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"

	"mcp-gateway/internal/validation"
)

// credentialsFromRequest reads the instance credentials from the multipart
// form, per runner. Google templates upload a service-account JSON file
// ("credentials"); Neo4j templates send connection fields (neo4j_uri,
// neo4j_username, neo4j_password, neo4j_database), serialized here to the
// JSON the Neo4j runner expects. Every error is a client error (400) and
// never contains the password.
func credentialsFromRequest(r *http.Request, runnerName string) ([]byte, error) {
	if runnerName == RunnerNeo4j {
		creds, err := validation.ValidateNeo4jCredentials(validation.Neo4jCredentials{
			URI:      multipartValue(r, "neo4j_uri"),
			Username: multipartValue(r, "neo4j_username"),
			Password: multipartValue(r, "neo4j_password"),
			Database: multipartValue(r, "neo4j_database"),
		})
		if err != nil {
			return nil, fmt.Errorf("invalid credentials: %w", err)
		}
		return json.Marshal(creds)
	}
	file, hdr, err := r.FormFile("credentials")
	if err != nil {
		return nil, errors.New("missing credentials file")
	}
	defer file.Close()
	if hdr.Size > int64(validation.MaxSAJSONSize) {
		return nil, errors.New("credentials file too large")
	}
	credBytes, err := io.ReadAll(io.LimitReader(file, int64(validation.MaxSAJSONSize)+1))
	if err != nil {
		return nil, errors.New("read credentials: " + err.Error())
	}
	if _, err := validation.ValidateServiceAccountJSON(credBytes); err != nil {
		return nil, errors.New("invalid credentials: " + err.Error())
	}
	return credBytes, nil
}

// multipartValue reads a field from the parsed multipart body only. r.FormValue
// would also read the query string and urlencoded bodies, which the audit
// middleware stores, so a password must never be accepted from there.
func multipartValue(r *http.Request, key string) string {
	if r.MultipartForm == nil {
		return ""
	}
	if vs := r.MultipartForm.Value[key]; len(vs) > 0 {
		return vs[0]
	}
	return ""
}

// validateRunnerExtraEnv enforces runner-specific extra_env rules on top of
// the template's required_extra_env schema. Neo4j instances accept only
// NEO4J_READ_ONLY = "true" | "false": any other NEO4J_* key could redirect the
// connection (NEO4J_URL wins over NEO4J_URI in mcp-neo4j-cypher) or take the
// server off stdio.
func validateRunnerExtraEnv(runnerName string, extra map[string]string) error {
	if runnerName != RunnerNeo4j {
		return nil
	}
	for k, v := range extra {
		if k != "NEO4J_READ_ONLY" {
			return fmt.Errorf("extra_env: %q is not allowed for Neo4j templates (only NEO4J_READ_ONLY)", k)
		}
		if v != "true" && v != "false" {
			return errors.New(`extra_env: NEO4J_READ_ONLY must be "true" or "false"`)
		}
	}
	return nil
}
