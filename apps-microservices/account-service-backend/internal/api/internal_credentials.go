package api

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"

	"account-service/internal/db"
)

// NameLookup looks up an oauth2_clients row by its display name.
type NameLookup interface {
	GetByName(name string) (*db.OAuth2Client, error)
}

type InternalCredentialsDeps struct {
	Repo       NameLookup
	Decrypt    func([]byte) ([]byte, error)
	AdminToken string
}

// NewInternalCredentialsHandler exposes
//
//	GET /internal/credentials/{name}
//
// gated by `X-Admin-Token`. Returns the plaintext client_id +
// client_secret for the named service. The shared admin token is
// distributed only to trusted internal callers (api-gateway et al.),
// so they never need DB access or the AES encryption key.
func NewInternalCredentialsHandler(d InternalCredentialsDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		presented := r.Header.Get("X-Admin-Token")
		if d.AdminToken == "" ||
			subtle.ConstantTimeCompare([]byte(presented), []byte(d.AdminToken)) != 1 {
			writeJSONErr(w, http.StatusUnauthorized, "unauthorized", "missing or invalid X-Admin-Token")
			return
		}
		name := r.PathValue("name")
		if name == "" {
			writeJSONErr(w, http.StatusBadRequest, "invalid_request", "name path parameter required")
			return
		}
		c, err := d.Repo.GetByName(name)
		if err != nil {
			writeJSONErr(w, http.StatusNotFound, "not_found", "no active client with that name")
			return
		}
		if !c.IsActive {
			writeJSONErr(w, http.StatusNotFound, "not_found", "client inactive")
			return
		}
		plain, err := d.Decrypt(c.ClientSecretEnc)
		if err != nil {
			writeJSONErr(w, http.StatusInternalServerError, "server_error", "decrypt failed")
			return
		}
		uris := []string{}
		if c.RedirectURIs != nil && *c.RedirectURIs != "" {
			_ = json.Unmarshal([]byte(*c.RedirectURIs), &uris)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"client_id":     c.ClientID,
			"client_secret": string(plain),
			"redirect_uris": uris,
			"name":          c.Name,
		})
	})
}
