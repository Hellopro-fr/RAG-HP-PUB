package authserver

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type AuthorizeParams struct {
	ResponseType        string
	ClientID            string
	RedirectURI         string
	CodeChallenge       string
	CodeChallengeMethod string
	State               string
	Scope               string
}

func parseAuthorizeParams(r *http.Request) (*AuthorizeParams, error) {
	getValue := func(key string) string {
		if v := r.FormValue(key); v != "" {
			return v
		}
		return r.URL.Query().Get(key)
	}
	p := &AuthorizeParams{
		ResponseType:        getValue("response_type"),
		ClientID:            getValue("client_id"),
		RedirectURI:         getValue("redirect_uri"),
		CodeChallenge:       getValue("code_challenge"),
		CodeChallengeMethod: getValue("code_challenge_method"),
		State:               getValue("state"),
		Scope:               getValue("scope"),
	}
	if p.ResponseType != "code" {
		return nil, errors.New("response_type must be code")
	}
	if p.ClientID == "" {
		return nil, errors.New("client_id required")
	}
	if p.RedirectURI == "" {
		return nil, errors.New("redirect_uri required")
	}
	if p.CodeChallenge == "" {
		return nil, errors.New("code_challenge required (PKCE)")
	}
	if p.CodeChallengeMethod != "S256" {
		return nil, errors.New("code_challenge_method must be S256")
	}
	return p, nil
}

func isRegisteredRedirectURI(c *db.OAuth2Client, uri string) bool {
	if c.RedirectURIs == nil || *c.RedirectURIs == "" {
		return false
	}
	var uris []string
	if err := json.Unmarshal([]byte(*c.RedirectURIs), &uris); err != nil {
		return false
	}
	for _, registered := range uris {
		if registered == uri {
			return true
		}
	}
	return false
}
