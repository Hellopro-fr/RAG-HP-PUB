package logout

import (
	"strings"
	"testing"
)

func TestSignWebhook_DeterministicAndVerifiable(t *testing.T) {
	body := []byte(`{"sub":"a@x"}`)
	secret := "the-client-secret"
	sig1 := SignWebhook(secret, body)
	sig2 := SignWebhook(secret, body)
	if sig1 != sig2 {
		t.Fatal("signature should be deterministic")
	}
	if !strings.HasPrefix(sig1, "sha256=") {
		t.Fatalf("prefix: %q", sig1)
	}
	if !VerifyWebhook(secret, body, sig1) {
		t.Fatal("VerifyWebhook should accept its own output")
	}
	if VerifyWebhook("wrong", body, sig1) {
		t.Fatal("VerifyWebhook accepted wrong secret")
	}
}
