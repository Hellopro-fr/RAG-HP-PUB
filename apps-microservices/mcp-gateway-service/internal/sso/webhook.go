package sso

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
)

// SignaturePrefix is the algorithm tag we expect on the X-Account-Signature
// header. The full header value looks like "hmac-sha256=<hex digest>".
const SignaturePrefix = "hmac-sha256="

// VerifyWebhookSignature compares the HMAC-SHA256 of body (keyed with the
// per-client secret) to the value advertised in the signature header. The
// comparison is constant-time to prevent timing-based forgery attempts.
func VerifyWebhookSignature(secret, body []byte, header string) error {
	if !strings.HasPrefix(header, SignaturePrefix) {
		return errors.New("missing or malformed signature prefix")
	}
	got, err := hex.DecodeString(strings.TrimPrefix(header, SignaturePrefix))
	if err != nil {
		return errors.New("signature not valid hex")
	}
	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	expected := mac.Sum(nil)
	if !hmac.Equal(got, expected) {
		return errors.New("signature mismatch")
	}
	return nil
}
