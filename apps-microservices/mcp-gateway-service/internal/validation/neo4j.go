package validation

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

// MaxNeo4jFieldLength caps each connection field; real values are < 200 chars.
const MaxNeo4jFieldLength = 1024

// Neo4jCredentials is the connection a Neo4j template instance uses. It is
// JSON-encoded, encrypted into template_instances.encrypted_credentials, and
// sent to mcp-template-neo4j-service as credentials_json.
type Neo4jCredentials struct {
	URI      string `json:"uri"`
	Username string `json:"username"`
	Password string `json:"password"`
	Database string `json:"database"`
}

var neo4jSchemes = map[string]bool{
	"bolt": true, "bolt+s": true, "bolt+ssc": true,
	"neo4j": true, "neo4j+s": true, "neo4j+ssc": true,
}

var neo4jDatabaseRe = regexp.MustCompile(`^[A-Za-z0-9._-]{1,63}$`)

// ValidateNeo4jCredentials trims the admin-entered fields (never the password)
// and returns the normalized value to encrypt. Error messages never include
// the password, nor the URI (which may embed one).
func ValidateNeo4jCredentials(in Neo4jCredentials) (Neo4jCredentials, error) {
	out := Neo4jCredentials{
		URI:      strings.TrimSpace(in.URI),
		Username: strings.TrimSpace(in.Username),
		Password: in.Password,
		Database: strings.TrimSpace(in.Database),
	}
	for _, v := range []string{out.URI, out.Username, out.Password, out.Database} {
		if len(v) > MaxNeo4jFieldLength {
			return out, fmt.Errorf("field too long (max %d characters)", MaxNeo4jFieldLength)
		}
	}
	if out.URI == "" {
		return out, fmt.Errorf("uri is required")
	}
	u, err := url.Parse(out.URI)
	if err != nil {
		return out, fmt.Errorf("uri is not a valid URL")
	}
	if !neo4jSchemes[strings.ToLower(u.Scheme)] {
		return out, fmt.Errorf("uri scheme must be one of bolt, bolt+s, bolt+ssc, neo4j, neo4j+s, neo4j+ssc")
	}
	if u.User != nil {
		return out, fmt.Errorf("uri must not embed credentials; use the username and password fields")
	}
	if u.Hostname() == "" {
		return out, fmt.Errorf("uri must include a host")
	}
	if u.Path != "" && u.Path != "/" {
		return out, fmt.Errorf("uri must not contain a path; set the database field instead")
	}
	if out.Username == "" {
		return out, fmt.Errorf("username is required")
	}
	if strings.TrimSpace(out.Password) == "" {
		return out, fmt.Errorf("password is required")
	}
	if out.Database == "" {
		out.Database = "neo4j"
	}
	if !neo4jDatabaseRe.MatchString(out.Database) {
		return out, fmt.Errorf("database must match [A-Za-z0-9._-]{1,63}")
	}
	return out, nil
}
