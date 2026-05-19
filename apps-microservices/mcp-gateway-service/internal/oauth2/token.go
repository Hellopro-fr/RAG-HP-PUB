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
// Email holds the end-user identity for authorization_code/refresh_token
// grants. It is empty for client_credentials grants — there is no human
// behind those tokens, and downstream filters that depend on a user
// identity ("self" mode) must fail closed when the claim is missing.
type AccessTokenClaims struct {
	TokenType string `json:"token_type"`
	Email     string `json:"email,omitempty"`
	jwt.RegisteredClaims
}

// IssueAccessToken creates an HS256 JWT access token for the given client.
// userEmail must be the authenticated end-user's email for authorization_code
// and refresh_token grants; pass "" for client_credentials.
func IssueAccessToken(jwtSecret, clientID, userEmail string, ttlSeconds int) (string, int, error) {
	now := time.Now()
	claims := AccessTokenClaims{
		TokenType: "oauth2_access",
		Email:     userEmail,
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

// ValidateAccessToken validates an OAuth2 access token JWT and returns the
// client_id (subject) and the end-user email claim (empty for
// client_credentials grants).
func ValidateAccessToken(tokenStr, jwtSecret string) (clientID, userEmail string, err error) {
	token, err := jwt.ParseWithClaims(tokenStr, &AccessTokenClaims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("%w: unexpected signing method: %v", ErrInvalidToken, token.Header["alg"])
		}
		return []byte(jwtSecret), nil
	}, jwt.WithValidMethods([]string{"HS256"}))

	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return "", "", ErrTokenExpired
		}
		return "", "", fmt.Errorf("%w: %v", ErrInvalidToken, err)
	}

	claims, ok := token.Claims.(*AccessTokenClaims)
	if !ok || !token.Valid {
		return "", "", ErrInvalidToken
	}

	if claims.TokenType != "oauth2_access" {
		return "", "", fmt.Errorf("%w: not an OAuth2 access token", ErrInvalidToken)
	}

	if claims.Subject == "" {
		return "", "", fmt.Errorf("%w: missing subject (client_id)", ErrInvalidToken)
	}

	return claims.Subject, claims.Email, nil
}
