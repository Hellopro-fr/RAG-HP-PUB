package validation

import (
	"strings"
	"testing"
)

const validSA = `{
  "type": "service_account",
  "project_id": "my-project",
  "client_email": "bot@my-project.iam.gserviceaccount.com",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
}`

func TestValidateServiceAccountJSON_OK(t *testing.T) {
	info, err := ValidateServiceAccountJSON([]byte(validSA))
	if err != nil {
		t.Fatalf("want nil err, got %v", err)
	}
	if info.ClientEmail != "bot@my-project.iam.gserviceaccount.com" {
		t.Errorf("ClientEmail = %q", info.ClientEmail)
	}
	if info.ProjectID != "my-project" {
		t.Errorf("ProjectID = %q", info.ProjectID)
	}
}

func TestValidateServiceAccountJSON_Errors(t *testing.T) {
	cases := []struct {
		name   string
		input  string
		errSub string
	}{
		{"empty", ``, "parse"},
		{"bad type", strings.Replace(validSA, `"service_account"`, `"user"`, 1), "type must be service_account"},
		{"no email", strings.Replace(validSA, `"client_email": "bot@my-project.iam.gserviceaccount.com",`, ``, 1), "client_email"},
		{"no project", strings.Replace(validSA, `"project_id": "my-project",`, ``, 1), "project_id"},
		{"no private_key", strings.Replace(validSA, `"private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"`, `"private_key": ""`, 1), "private_key"},
		{"bad email domain", strings.Replace(validSA, "bot@my-project.iam.gserviceaccount.com", "bot@example.com", 1), "client_email"},
		{"subdomain bypass attempt", strings.Replace(validSA, "bot@my-project.iam.gserviceaccount.com", "bot@foo.iam.gserviceaccount.com.evil.com", 1), "client_email"},
		{"wrong PK format", strings.Replace(validSA, `-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n`, `not-a-pem`, 1), "private_key"},
		{"too big", `{"type":"service_account"` + strings.Repeat(" ", 17*1024) + `}`, "too large"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ValidateServiceAccountJSON([]byte(tc.input))
			if err == nil {
				t.Fatalf("want error")
			}
			if !strings.Contains(err.Error(), tc.errSub) {
				t.Errorf("err = %v, want substring %q", err, tc.errSub)
			}
		})
	}
}
