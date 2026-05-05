package sso

import (
	"testing"
	"time"
)

func TestPendingStateRoundTrip(t *testing.T) {
	secret := []byte("test-secret-32-bytes-of-padding!!")
	in := PendingState{
		Verifier: "verifier-xyz",
		State:    "nonce-abc",
		ReturnTo: "/dashboard",
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
	}
	tok, err := SignPendingState(secret, in)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	out, err := VerifyPendingState(secret, tok)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if out.Verifier != in.Verifier || out.State != in.State || out.ReturnTo != in.ReturnTo {
		t.Fatalf("round-trip mismatch: %+v vs %+v", in, out)
	}
}

func TestPendingStateExpired(t *testing.T) {
	secret := []byte("test-secret-32-bytes-of-padding!!")
	in := PendingState{
		Verifier: "v",
		State:    "s",
		ReturnTo: "/",
		Exp:      time.Now().Add(-1 * time.Second).Unix(),
	}
	tok, _ := SignPendingState(secret, in)
	if _, err := VerifyPendingState(secret, tok); err == nil {
		t.Fatal("expected expiry error")
	}
}

func TestPendingStateTampered(t *testing.T) {
	secret := []byte("test-secret-32-bytes-of-padding!!")
	tok, _ := SignPendingState(secret, PendingState{
		Verifier: "v", State: "s", ReturnTo: "/", Exp: time.Now().Add(time.Minute).Unix(),
	})
	tampered := tok[:len(tok)-1] + "x"
	if _, err := VerifyPendingState(secret, tampered); err == nil {
		t.Fatal("expected signature error")
	}
}
