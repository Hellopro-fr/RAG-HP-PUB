package oauth2

import (
	"testing"
	"time"
)

func TestCache_SetAndGet(t *testing.T) {
	c := NewCache(60 * time.Second)
	cc := &CachedClient{
		ID:        "client-1",
		ServerIDs: map[string]bool{"srv-1": true},
		IsActive:  true,
	}
	c.Set("client-1", cc)

	got, ok := c.Get("client-1")
	if !ok {
		t.Fatal("expected cache hit")
	}
	if got.ID != "client-1" {
		t.Fatalf("expected ID=client-1, got %s", got.ID)
	}
}

func TestCache_Miss(t *testing.T) {
	c := NewCache(60 * time.Second)
	_, ok := c.Get("nonexistent")
	if ok {
		t.Fatal("expected cache miss")
	}
}

func TestCache_Invalidate(t *testing.T) {
	c := NewCache(60 * time.Second)
	c.Set("client-1", &CachedClient{ID: "client-1"})
	c.Invalidate("client-1")
	_, ok := c.Get("client-1")
	if ok {
		t.Fatal("expected cache miss after invalidate")
	}
}
