package auth

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestGenerateAndVerifyAccessToken(t *testing.T) {
	j := NewJWT("secret", "HS256", 15*time.Minute)

	tok := j.GenerateAccessToken("svc", 42)
	require.NotEmpty(t, tok)

	claims, err := j.VerifyAccessToken(tok)
	require.NoError(t, err)
	require.Equal(t, "svc", claims.Subject)
	require.Equal(t, uint(42), claims.RefreshTokenID)
}

func TestVerifyExpired(t *testing.T) {
	j := NewJWT("secret", "HS256", -time.Minute)
	tok := j.GenerateAccessToken("svc", 1)
	_, err := j.VerifyAccessToken(tok)
	require.ErrorIs(t, err, ErrExpired)
}

func TestVerifyInvalid(t *testing.T) {
	j := NewJWT("secret", "HS256", time.Minute)
	_, err := j.VerifyAccessToken("not-a-jwt")
	require.ErrorIs(t, err, ErrInvalid)
}

func TestRefreshTokenHasNoExp(t *testing.T) {
	j := NewJWT("secret", "HS256", time.Minute)
	tok := j.GenerateRefreshToken("svc")
	c, err := j.parse(tok)
	require.NoError(t, err)
	require.Equal(t, "svc", c["sub"])
	require.Equal(t, "refresh", c["type"])
	_, hasExp := c["exp"]
	require.False(t, hasExp)
}
