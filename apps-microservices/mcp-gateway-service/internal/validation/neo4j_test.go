package validation

import (
	"strings"
	"testing"
)

func TestValidateNeo4jCredentials_OK(t *testing.T) {
	got, err := ValidateNeo4jCredentials(Neo4jCredentials{
		URI: "  bolt://neo4j:7687 ", Username: " reader ", Password: " p w ", Database: "",
	})
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	want := Neo4jCredentials{URI: "bolt://neo4j:7687", Username: "reader", Password: " p w ", Database: "neo4j"}
	if got != want {
		t.Errorf("got %+v, want %+v", got, want)
	}
	for _, uri := range []string{"bolt+s://h:7687", "bolt+ssc://h", "neo4j://h:7687", "neo4j+s://h.example.com", "neo4j+ssc://10.0.0.1:7687", "NEO4J://h", "neo4j://h:7687?policy=eu", "bolt://h:7687/"} {
		if _, err := ValidateNeo4jCredentials(Neo4jCredentials{URI: uri, Username: "u", Password: "p"}); err != nil {
			t.Errorf("%s: unexpected err %v", uri, err)
		}
	}
}

func TestValidateNeo4jCredentials_Errors(t *testing.T) {
	long := strings.Repeat("a", MaxNeo4jFieldLength+1)
	cases := []struct {
		name   string
		in     Neo4jCredentials
		errSub string
	}{
		{"empty uri", Neo4jCredentials{Username: "u", Password: "hunter2"}, "uri is required"},
		{"http scheme", Neo4jCredentials{URI: "http://h:7474", Username: "u", Password: "hunter2"}, "uri scheme must be one of"},
		{"no host", Neo4jCredentials{URI: "bolt://", Username: "u", Password: "hunter2"}, "uri must include a host"},
		{"userinfo", Neo4jCredentials{URI: "bolt://neo4j:hunter2@h:7687", Username: "u", Password: "hunter2"}, "must not embed credentials"},
		{"path", Neo4jCredentials{URI: "bolt://h:7687/db", Username: "u", Password: "hunter2"}, "must not contain a path"},
		{"no username", Neo4jCredentials{URI: "bolt://h", Password: "hunter2"}, "username is required"},
		{"blank password", Neo4jCredentials{URI: "bolt://h", Username: "u", Password: "   "}, "password is required"},
		{"bad database", Neo4jCredentials{URI: "bolt://h", Username: "u", Password: "hunter2", Database: "a b"}, "database must match"},
		{"too long", Neo4jCredentials{URI: "bolt://h", Username: long, Password: "hunter2"}, "too long"},
	}
	for _, c := range cases {
		_, err := ValidateNeo4jCredentials(c.in)
		if err == nil || !strings.Contains(err.Error(), c.errSub) {
			t.Errorf("%s: err = %v, want containing %q", c.name, err, c.errSub)
			continue
		}
		if strings.Contains(err.Error(), "hunter2") {
			t.Errorf("%s: error echoes the password: %v", c.name, err)
		}
	}
}
