// Package routing decides which upstream Zoho URL serves a given caller.
package routing

import "strings"

// matchesUserEmail returns true when serverCreatedBy and the caller identify
// the same person. Resolution order:
//  1. case-insensitive exact-email equality (when both are non-empty);
//  2. login-portion (local-part before '@') case-insensitive equality;
//
// When serverCreatedBy has no local-part (e.g. "@hp.fr"), the function never
// matches anyone.
func matchesUserEmail(serverCreatedBy, endUserEmail, endUserLogin string) bool {
	if serverCreatedBy == "" {
		return false
	}
	if endUserEmail != "" && strings.EqualFold(serverCreatedBy, endUserEmail) {
		return true
	}
	serverLogin := loginPart(serverCreatedBy)
	if serverLogin == "" {
		return false
	}
	if endUserLogin != "" && strings.EqualFold(serverLogin, endUserLogin) {
		return true
	}
	if endUserEmail != "" && strings.EqualFold(serverLogin, loginPart(endUserEmail)) {
		return true
	}
	return false
}

// loginPart returns the local-part of an email (everything before '@').
// When the input has no '@', the whole string is treated as the login
// (matches how imports store bare logins like "haingatiana"). Returns ""
// only when the input starts with '@' (no local-part).
func loginPart(email string) string {
	at := strings.IndexByte(email, '@')
	if at < 0 {
		return email
	}
	if at == 0 {
		return ""
	}
	return email[:at]
}
