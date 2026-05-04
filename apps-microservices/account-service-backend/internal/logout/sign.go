package logout

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
)

func SignWebhook(secret string, body []byte) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(body)
	return "sha256=" + hex.EncodeToString(h.Sum(nil))
}

func VerifyWebhook(secret string, body []byte, sig string) bool {
	want := SignWebhook(secret, body)
	if len(sig) != len(want) {
		return false
	}
	return hmac.Equal([]byte(want), []byte(sig))
}
