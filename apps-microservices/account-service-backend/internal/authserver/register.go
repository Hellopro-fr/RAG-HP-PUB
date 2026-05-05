package authserver

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"

	"account-service/internal/db"
)

type ClientCreator interface {
	Create(c *db.OAuth2Client) error
}

type EncryptFunc func([]byte) ([]byte, error)

type RegisterDeps struct {
	Creator ClientCreator
	Encrypt EncryptFunc
}

type registerRequest struct {
	ClientName       string   `json:"client_name"`
	RedirectURIs     []string `json:"redirect_uris"`
	LogoutWebhookURL string   `json:"logout_webhook_url,omitempty"`
}

func NewRegisterHandler(d RegisterDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body registerRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", err.Error())
			return
		}
		if body.ClientName == "" || len(body.RedirectURIs) == 0 {
			writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "client_name and redirect_uris required")
			return
		}
		clientID, err := newRandomB64(24)
		if err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
			return
		}
		secret, err := newRandomB64(32)
		if err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
			return
		}
		enc, err := d.Encrypt([]byte(secret))
		if err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "encrypt failed")
			return
		}
		urisJSON, _ := json.Marshal(body.RedirectURIs)
		urisStr := string(urisJSON)
		c := &db.OAuth2Client{
			ClientID:          clientID,
			ClientSecretEnc:   enc,
			Name:              body.ClientName,
			RedirectURIs:      &urisStr,
			LogoutWebhookURL:  body.LogoutWebhookURL,
			TokenTTLSeconds:   60,
			RefreshTTLSeconds: 2592000,
			IsActive:          true,
		}
		if err := d.Creator.Create(c); err != nil {
			writeOAuthErr(w, http.StatusInternalServerError, "server_error", "create failed")
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"client_id":     clientID,
			"client_secret": secret,
			"client_name":   c.Name,
			"redirect_uris": body.RedirectURIs,
		})
	})
}

func newRandomB64(n int) (string, error) {
	buf := make([]byte, n)
	if _, err := io.ReadFull(rand.Reader, buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}
