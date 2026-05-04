package auth

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

const sessionCookieName = "account_session"

type SessionData struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
	Token       string `json:"token"`
}

func SetSession(w http.ResponseWriter, secret string, data SessionData, secure bool) error {
	body, err := json.Marshal(data)
	if err != nil {
		return err
	}
	claims := Claims{
		Sub:   data.Email,
		Email: data.Email,
		Name:  data.DisplayName,
		Aud:   "session",
		Iat:   time.Now().Unix(),
		Exp:   time.Now().Add(24 * time.Hour).Unix(),
	}
	tok, err := SignJWT(secret, claims)
	if err != nil {
		return err
	}
	enc := base64.RawURLEncoding.EncodeToString(body)
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    fmt.Sprintf("%s.%s", tok, enc),
		Path:     "/",
		MaxAge:   24 * 60 * 60,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   secure,
	})
	return nil
}

func GetSession(r *http.Request, secret string) (*SessionData, error) {
	c, err := r.Cookie(sessionCookieName)
	if err != nil {
		return nil, err
	}
	idx := strings.LastIndex(c.Value, ".")
	if idx <= 0 || idx == len(c.Value)-1 {
		return nil, errors.New("malformed session cookie")
	}
	tokenPart, dataPart := c.Value[:idx], c.Value[idx+1:]
	if _, err := ValidateJWT(tokenPart, secret, "session"); err != nil {
		return nil, err
	}
	body, err := base64.RawURLEncoding.DecodeString(dataPart)
	if err != nil {
		return nil, err
	}
	var d SessionData
	if err := json.Unmarshal(body, &d); err != nil {
		return nil, err
	}
	return &d, nil
}

func ClearSession(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		HttpOnly: true,
	})
}
