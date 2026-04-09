package auth

import (
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var (
	ErrTokenExpired = errors.New("token expired")
	ErrTokenInvalid = errors.New("invalid token")
)

// Claims represents the JWT payload.
type Claims struct {
	Audience string `json:"aud,omitempty"`
	Exp      int64  `json:"exp,omitempty"`
	Iat      int64  `json:"iat,omitempty"`
	Name     string `json:"name,omitempty"`
	Email    string `json:"email,omitempty"`
	jwt.RegisteredClaims
}

// SignJWT creates an HS256 JWT with the given claims.
func SignJWT(secret string, claims Claims) (string, error) {
	claims.RegisteredClaims = jwt.RegisteredClaims{
		ExpiresAt: jwt.NewNumericDate(time.Unix(claims.Exp, 0)),
		IssuedAt:  jwt.NewNumericDate(time.Unix(claims.Iat, 0)),
	}
	if claims.Audience != "" {
		claims.RegisteredClaims.Audience = jwt.ClaimStrings{claims.Audience}
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

// ValidateJWT decodes and validates an HS256 JWT.
// It strictly enforces that the token uses the HS256 algorithm.
func ValidateJWT(tokenStr, secret, audience string) (*Claims, error) {
	parserOpts := []jwt.ParserOption{
		jwt.WithValidMethods([]string{"HS256"}),
		// Do not use WithAudience — external auth tokens may omit aud claim.
		// Audience is checked manually below when present.
	}

	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		// Double-check algorithm to prevent alg:none or alg switching attacks
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("%w: unexpected signing method: %v", ErrTokenInvalid, token.Header["alg"])
		}
		return []byte(secret), nil
	}, parserOpts...)

	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrTokenExpired
		}
		return nil, fmt.Errorf("%w: %v", ErrTokenInvalid, err)
	}

	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, ErrTokenInvalid
	}

	// Check audience manually: only enforce if the token carries an aud claim
	if audience != "" && claims.Audience != "" && claims.Audience != audience {
		return nil, fmt.Errorf("%w: audience mismatch", ErrTokenInvalid)
	}

	// Reject tokens with iat in the future (clock-skew attack, 5min tolerance)
	if claims.Iat > 0 && time.Unix(claims.Iat, 0).After(time.Now().Add(5*time.Minute)) {
		return nil, fmt.Errorf("%w: token issued in the future", ErrTokenInvalid)
	}

	return claims, nil
}
