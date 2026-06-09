package tests

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestWSPubSub_BroadcastsToHub(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer rdb.Close()
	hub := ws.NewHub()
	c := ws.NewClientForTest()
	hub.Register(c)
	ps := ws.NewPubSub(rdb, hub, "crawl_updates")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)
	time.Sleep(150 * time.Millisecond)
	rdb.Publish(context.Background(), "crawl_updates", `{"x":1}`)
	select {
	case msg := <-c.SendForTest():
		if string(msg) != `{"x":1}` {
			t.Errorf("msg = %s", msg)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("no broadcast received")
	}
}

func TestWSPubSub_CrawlUpdateEmitsJobUpdate(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer rdb.Close()
	hub := ws.NewHub()
	c := ws.NewClientForTest()
	hub.Register(c)
	ps := ws.NewPubSub(rdb, hub, "crawl_updates")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)
	time.Sleep(150 * time.Millisecond)
	rdb.Publish(context.Background(), "crawl_updates", `{"crawl_id":"abc","status":"finished","timestamp":"2026-06-09T10:00:00Z"}`)
	select {
	case raw := <-c.SendForTest():
		var msg map[string]any
		if err := json.Unmarshal(raw, &msg); err != nil {
			t.Fatalf("invalid JSON: %v", err)
		}
		if msg["type"] != "job_update" {
			t.Errorf("expected type=job_update, got %v", msg["type"])
		}
		if msg["crawl_id"] != "abc" {
			t.Errorf("expected crawl_id=abc, got %v", msg["crawl_id"])
		}
	case <-time.After(3 * time.Second):
		t.Fatal("no broadcast received")
	}
}
