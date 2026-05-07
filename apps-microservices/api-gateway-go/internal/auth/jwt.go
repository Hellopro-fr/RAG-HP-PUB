package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var (
	ErrExpired = errors.New("token expired")
	ErrInvalid = errors.New("token invalid")
)

type AccessClaims struct {
	Subject        string
	RefreshTokenID uint
}

type JWT struct {
	secret []byte
	alg    string
	access time.Duration
}

func NewJWT(secret, alg string, accessDuration time.Duration) *JWT {
	return &JWT{secret: []byte(secret), alg: alg, access: accessDuration}
}

func (j *JWT) GenerateAccessToken(service string, refreshID uint) string {
	now := time.Now().UTC()
	claims := jwt.MapClaims{
		"sub":  service,
		"rtid": refreshID,
		"iat":  now.Unix(),
		"exp":  now.Add(j.access).Unix(),
	}
	tok := jwt.NewWithClaims(jwt.GetSigningMethod(j.alg), claims)
	s, _ := tok.SignedString(j.secret)
	return s
}

func (j *JWT) GenerateRefreshToken(service string) string {
	claims := jwt.MapClaims{
		"sub":  service,
		"type": "refresh",
		"iat":  time.Now().UTC().Unix(),
	}
	tok := jwt.NewWithClaims(jwt.GetSigningMethod(j.alg), claims)
	s, _ := tok.SignedString(j.secret)
	return s
}

func (j *JWT) VerifyAccessToken(raw string) (AccessClaims, error) {
	c, err := j.parse(raw)
	if err != nil {
		return AccessClaims{}, err
	}
	sub, _ := c["sub"].(string)
	var rtid uint
	switch v := c["rtid"].(type) {
	case float64:
		rtid = uint(v)
	case int64:
		rtid = uint(v)
	}
	return AccessClaims{Subject: sub, RefreshTokenID: rtid}, nil
}

func (j *JWT) parse(raw string) (jwt.MapClaims, error) {
	tok, err := jwt.Parse(raw, func(t *jwt.Token) (interface{}, error) {
		return j.secret, nil
	}, jwt.WithValidMethods([]string{j.alg}))
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrExpired
		}
		return nil, ErrInvalid
	}
	c, ok := tok.Claims.(jwt.MapClaims)
	if !ok {
		return nil, ErrInvalid
	}
	return c, nil
}

// VerifyDocsToken decodes a docs-session JWT, skipping audience verification
// (matches Python DocsAuthMiddleware which sets options={"verify_aud": False}).
func (j *JWT) VerifyDocsToken(raw string) error {
	_, err := j.parse(raw)
	return err
}
