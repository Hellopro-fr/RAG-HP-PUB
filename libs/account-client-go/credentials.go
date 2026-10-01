// Package accountclient resolves account-service OAuth2 client credentials
// by SERVICE_NAME. Convention mirrors libs/common-utils/sso/credentials.py:
//
//	SERVICE_NAME=api-gateway
//	  -> ACCOUNT_CLIENT_ID_API_GATEWAY
//	  -> ACCOUNT_CLIENT_SECRET_API_GATEWAY
//
// If the prefixed pair is not set, falls back to plain ACCOUNT_CLIENT_ID and
// ACCOUNT_CLIENT_SECRET so single-service stacks keep working unchanged.
package accountclient

import (
	"errors"
	"os"
	"regexp"
	"strings"
)

// ErrCredentialsMissing is returned when neither the prefixed nor the
// fallback env vars are set.
var ErrCredentialsMissing = errors.New("account-service credentials not configured: " +
	"set ACCOUNT_CLIENT_ID_<SERVICE_NAME> + ACCOUNT_CLIENT_SECRET_<SERVICE_NAME>, " +
	"or plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET as fallback")

var slugRe = regexp.MustCompile(`[^A-Z0-9]+`)

// DeriveEnvKeys maps a service name to the (clientIDEnv, clientSecretEnv) pair.
//
//	DeriveEnvKeys("api-gateway")
//	  -> "ACCOUNT_CLIENT_ID_API_GATEWAY", "ACCOUNT_CLIENT_SECRET_API_GATEWAY"
func DeriveEnvKeys(serviceName string) (string, string) {
	slug := strings.Trim(slugRe.ReplaceAllString(strings.ToUpper(serviceName), "_"), "_")
	return "ACCOUNT_CLIENT_ID_" + slug, "ACCOUNT_CLIENT_SECRET_" + slug
}

// GetCredentials returns (clientID, clientSecret) for the named service.
// If serviceName is empty, reads SERVICE_NAME from the environment.
// Falls back to plain ACCOUNT_CLIENT_ID / ACCOUNT_CLIENT_SECRET when the
// prefixed pair is not set.
func GetCredentials(serviceName string) (string, string, error) {
	name := serviceName
	if name == "" {
		name = strings.TrimSpace(os.Getenv("SERVICE_NAME"))
	}

	if name != "" {
		idKey, secKey := DeriveEnvKeys(name)
		cid := os.Getenv(idKey)
		sec := os.Getenv(secKey)
		if cid != "" && sec != "" {
			return cid, sec, nil
		}
	}

	cid := os.Getenv("ACCOUNT_CLIENT_ID")
	sec := os.Getenv("ACCOUNT_CLIENT_SECRET")
	if cid != "" && sec != "" {
		return cid, sec, nil
	}

	return "", "", ErrCredentialsMissing
}
