package tests

import (
	"context"
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
