package sso

import (
	"crypto/sha256"
	"encoding/base64"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestNewPKCEPair(t *testing.T) {
	p := NewPKCEPair()
	require.NotEmpty(t, p.Verifier)
	require.NotEmpty(t, p.Challenge)
	require.NotEmpty(t, p.State)
	require.False(t, strings.HasSuffix(p.Challenge, "="))

	sum := sha256.Sum256([]byte(p.Verifier))
	want := base64.RawURLEncoding.EncodeToString(sum[:])
	require.Equal(t, want, p.Challenge)
}
