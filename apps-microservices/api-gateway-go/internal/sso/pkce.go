package sso

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
)

type PKCEPair struct {
	Verifier  string
	Challenge string
	State     string
}

func b64url(b []byte) string { return base64.RawURLEncoding.EncodeToString(b) }

func NewPKCEPair() PKCEPair {
	verifierBytes := make([]byte, 32)
	_, _ = rand.Read(verifierBytes)
	verifier := b64url(verifierBytes)

	sum := sha256.Sum256([]byte(verifier))
	challenge := b64url(sum[:])

	stateBytes := make([]byte, 16)
	_, _ = rand.Read(stateBytes)
	state := b64url(stateBytes)

	return PKCEPair{Verifier: verifier, Challenge: challenge, State: state}
}
