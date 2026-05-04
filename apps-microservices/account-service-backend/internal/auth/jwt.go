package auth

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
)

type Claims struct {
	Sub     string                 `json:"sub,omitempty"`
	Email   string                 `json:"email,omitempty"`
	Name    string                 `json:"name,omitempty"`
	Aud     string                 `json:"aud"`
	Iss     string                 `json:"iss,omitempty"`
	Sid     string                 `json:"sid,omitempty"`
	Iat     int64                  `json:"iat"`
	Exp     int64                  `json:"exp"`
	IsAdmin bool                   `json:"is_admin,omitempty"`
	Custom  map[string]interface{} `json:"-"`
}

func (c Claims) toMap() jwt.MapClaims {
	m := jwt.MapClaims{
		"aud": c.Aud,
		"exp": c.Exp,
		"iat": c.Iat,
	}
	if c.Sub != "" {
		m["sub"] = c.Sub
	}
	if c.Email != "" {
		m["email"] = c.Email
	}
	if c.Name != "" {
		m["name"] = c.Name
	}
	if c.Iss != "" {
		m["iss"] = c.Iss
	}
	if c.Sid != "" {
		m["sid"] = c.Sid
	}
	if c.IsAdmin {
		m["is_admin"] = true
	}
	for k, v := range c.Custom {
		m[k] = v
	}
	return m
}

func SignJWT(secret string, c Claims) (string, error) {
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, c.toMap())
	return tok.SignedString([]byte(secret))
}

func ValidateJWT(token, secret, expectedAud string) (*Claims, error) {
	parsed, err := jwt.Parse(token, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return []byte(secret), nil
	})
	if err != nil || !parsed.Valid {
		return nil, fmt.Errorf("invalid token: %w", err)
	}
	mc, ok := parsed.Claims.(jwt.MapClaims)
	if !ok {
		return nil, errors.New("unexpected claims type")
	}
	if expectedAud != "" {
		if aud, _ := mc["aud"].(string); aud != expectedAud {
			return nil, fmt.Errorf("audience mismatch: %q != %q", aud, expectedAud)
		}
	}
	out := &Claims{Custom: map[string]interface{}{}}
	for k, v := range mc {
		switch k {
		case "sub":
			out.Sub, _ = v.(string)
		case "email":
			out.Email, _ = v.(string)
		case "name":
			out.Name, _ = v.(string)
		case "aud":
			out.Aud, _ = v.(string)
		case "iss":
			out.Iss, _ = v.(string)
		case "sid":
			out.Sid, _ = v.(string)
		case "iat":
			if f, ok := v.(float64); ok {
				out.Iat = int64(f)
			}
		case "exp":
			if f, ok := v.(float64); ok {
				out.Exp = int64(f)
			}
		case "is_admin":
			out.IsAdmin, _ = v.(bool)
		default:
			out.Custom[k] = v
		}
	}
	return out, nil
}
