package oauth2

import (
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var (
	ErrInvalidToken = errors.New("invalid access token")
	ErrTokenExpired = errors.New("access token expired")
)

// AccessTokenClaims represents the JWT claims for an OAuth2 access token.
type AccessTokenClaims struct {
	TokenType string `json:"token_type"`
	jwt.RegisteredClaims
}

// IssueAccessToken creates an HS256 JWT access token for the given client.
func IssueAccessToken(jwtSecret, clientID string, ttlSeconds int) (string, int, error) {
	now := time.Now()
	claims := AccessTokenClaims{
		TokenType: "oauth2_access",
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   clientID,
			Issuer:    "mcp-gateway",
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(time.Duration(ttlSeconds) * time.Second)),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString([]byte(jwtSecret))
	if err != nil {
		return "", 0, fmt.Errorf("sign access token: %w", err)
	}

	return tokenStr, ttlSeconds, nil
}

// ValidateAccessToken validates an OAuth2 access token JWT and returns the client_id (subject).
func ValidateAccessToken(tokenStr, jwtSecret string) (string, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &AccessTokenClaims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("%w: unexpected signing method: %v", ErrInvalidToken, token.Header["alg"])
		}
		return []byte(jwtSecret), nil
	}, jwt.WithValidMethods([]string{"HS256"}))

	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return "", ErrTokenExpired
		}
		return "", fmt.Errorf("%w: %v", ErrInvalidToken, err)
	}

	claims, ok := token.Claims.(*AccessTokenClaims)
	if !ok || !token.Valid {
		return "", ErrInvalidToken
	}

	if claims.TokenType != "oauth2_access" {
		return "", fmt.Errorf("%w: not an OAuth2 access token", ErrInvalidToken)
	}

	if claims.Subject == "" {
		return "", fmt.Errorf("%w: missing subject (client_id)", ErrInvalidToken)
	}

	return claims.Subject, nil
}
