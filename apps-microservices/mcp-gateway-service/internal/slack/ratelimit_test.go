package slack

import (
	"testing"
	"time"
)

func TestCooldownLimiter_FirstCallAllowed(t *testing.T) {
	l := NewCooldownLimiter(1 * time.Second)
	if !l.Allow("1.2.3.4|/mcp") {
		t.Fatal("first call should be allowed")
	}
}

func TestCooldownLimiter_BlocksWithinCooldown(t *testing.T) {
	l := NewCooldownLimiter(1 * time.Second)
	l.Allow("k")
	if l.Allow("k") {
		t.Fatal("second call within cooldown should be blocked")
	}
}

func TestCooldownLimiter_DifferentKeyAllowed(t *testing.T) {
	l := NewCooldownLimiter(1 * time.Second)
	l.Allow("1.2.3.4|/mcp")
	if !l.Allow("5.6.7.8|/mcp") {
		t.Fatal("different IP should be allowed")
	}
	if !l.Allow("1.2.3.4|/sse") {
		t.Fatal("different endpoint should be allowed")
	}
}

func TestCooldownLimiter_ExpiresAfterCooldown(t *testing.T) {
	l := NewCooldownLimiter(20 * time.Millisecond)
	l.Allow("k")
	time.Sleep(40 * time.Millisecond)
	if !l.Allow("k") {
		t.Fatal("after cooldown expiry call should be allowed")
	}
}

func TestCooldownLimiter_ZeroCooldownAlwaysAllows(t *testing.T) {
	l := NewCooldownLimiter(0)
	for i := 0; i < 5; i++ {
		if !l.Allow("k") {
			t.Fatalf("zero cooldown call %d should be allowed", i)
		}
	}
}
