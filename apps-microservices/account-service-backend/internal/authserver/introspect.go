package authserver

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"net/http"

	"account-service/internal/auth"
	"account-service/internal/db"
)

type Revoker interface {
	RevokeBySID(sid, reason string) error
}

type RevokeDeps struct {
	ClientRepo ClientRepo
	Rotator    RefreshRotator
	Revoker    Revoker
	Decrypt    DecryptFunc
}

func NewRevokeHandler(d RevokeDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		_ = r.ParseForm()
		clientID, secret, ok := extractClientAuth(r)
		cli, err := d.ClientRepo.GetByClientID(clientID)
		if !ok || err != nil {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		plain, err := d.Decrypt(cli.ClientSecretEnc)
		if err != nil || subtle.ConstantTimeCompare(plain, []byte(secret)) != 1 {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		raw := r.FormValue("token")
		row, err := d.Rotator.FindByHash(HashRefreshToken(raw))
		if err == nil {
			_ = d.Revoker.RevokeBySID(row.SID, "user_logout")
		}
		// RFC 7009: always 200 OK regardless of token validity
		w.WriteHeader(http.StatusOK)
	})
}

type IntrospectDeps struct {
	ClientRepo ClientRepo
	Rotator    RefreshRotator
	Decrypt    DecryptFunc
	JWTSecret  string
	Issuer     string
	Audience   string
}

func NewIntrospectHandler(d IntrospectDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		_ = r.ParseForm()
		clientID, secret, ok := extractClientAuth(r)
		cli, err := d.ClientRepo.GetByClientID(clientID)
		if !ok || err != nil {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		plain, err := d.Decrypt(cli.ClientSecretEnc)
		if err != nil || subtle.ConstantTimeCompare(plain, []byte(secret)) != 1 {
			writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "")
			return
		}
		tok := r.FormValue("token")
		claims, err := auth.ValidateJWT(tok, d.JWTSecret, d.Audience)
		if err != nil {
			respondInactive(w)
			return
		}
		if claims.Sid != "" {
			rows, err := listRowsBySID(d.Rotator, claims.Sid)
			if err == nil && allRevoked(rows) {
				respondInactive(w)
				return
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"active": true,
			"sub":    claims.Sub,
			"sid":    claims.Sid,
			"exp":    claims.Exp,
			"iat":    claims.Iat,
			"aud":    claims.Aud,
			"iss":    claims.Iss,
		})
	})
}

func respondInactive(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"active": false})
}

func listRowsBySID(rot RefreshRotator, sid string) ([]*db.OAuth2RefreshToken, error) {
	if lister, ok := rot.(interface {
		ListBySID(string) ([]db.OAuth2RefreshToken, error)
	}); ok {
		rows, err := lister.ListBySID(sid)
		if err != nil {
			return nil, err
		}
		out := make([]*db.OAuth2RefreshToken, len(rows))
		for i := range rows {
			out[i] = &rows[i]
		}
		return out, nil
	}
	return nil, errors.New("no lister")
}

func allRevoked(rows []*db.OAuth2RefreshToken) bool {
	if len(rows) == 0 {
		return false
	}
	for _, r := range rows {
		if !r.Revoked {
			return false
		}
	}
	return true
}
