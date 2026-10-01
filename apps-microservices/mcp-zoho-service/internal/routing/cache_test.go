package routing

import (
	"testing"
	"time"
)

func TestCache_HitMissExpire(t *testing.T) {
	c := newCache(100 * time.Millisecond)

	if _, ok := c.get("alice@hp.fr"); ok {
		t.Fatalf("expected miss")
	}

	value := &Resolution{UpstreamURL: "http://upstream/a", Headers: map[string]string{"k": "v"}}
	c.set("alice@hp.fr", value)

	got, ok := c.get("alice@hp.fr")
	if !ok || got.UpstreamURL != "http://upstream/a" {
		t.Fatalf("expected hit with URL, got ok=%v val=%+v", ok, got)
	}

	time.Sleep(120 * time.Millisecond)

	if _, ok := c.get("alice@hp.fr"); ok {
		t.Fatalf("expected expiry miss")
	}
}
