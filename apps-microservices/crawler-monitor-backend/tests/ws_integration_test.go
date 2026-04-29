package tests

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

func TestWSIntegration_50Clients_500Messages(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	rs, _ := redisstore.New("redis://" + mr.Addr())

	hub := ws.NewHub()
	defer hub.Close()
	ps := ws.NewPubSub(rdb, hub, "crawl_updates")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)

	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}, Hub: hub,
	}))
	defer srv.Close()
	wsURL := strings.Replace(srv.URL, "http", "ws", 1) + "/?token=" + mintToken("admin", "test-secret")

	const N = 50
	const MSG = 500
	conns := make([]*websocket.Conn, N)
	received := make([]atomic.Int64, N)
	var wg sync.WaitGroup
	for i := 0; i < N; i++ {
		c, _, err := websocket.DefaultDialer.Dial(wsURL, http.Header{})
		if err != nil {
			t.Fatalf("dial %d: %v", i, err)
		}
		conns[i] = c
		wg.Add(1)
		go func(i int, c *websocket.Conn) {
			defer wg.Done()
			_ = c.SetReadDeadline(time.Now().Add(20 * time.Second))
			for {
				_, _, err := c.ReadMessage()
				if err != nil {
					return
				}
				if received[i].Add(1) >= MSG {
					return
				}
			}
		}(i, c)
	}
	time.Sleep(500 * time.Millisecond)
	for i := 0; i < MSG; i++ {
		rdb.Publish(context.Background(), "crawl_updates", []byte(fmt.Sprintf(`{"i":%d}`, i)))
	}
	doneCh := make(chan struct{})
	go func() { wg.Wait(); close(doneCh) }()
	select {
	case <-doneCh:
	case <-time.After(15 * time.Second):
		for _, c := range conns {
			_ = c.Close()
		}
	}
	missing := 0
	for i := 0; i < N; i++ {
		if received[i].Load() < int64(MSG*90/100) {
			missing++
			t.Logf("client %d: %d/%d", i, received[i].Load(), MSG)
		}
	}
	if missing > 0 {
		t.Errorf("%d/%d clients received < 90%% of messages", missing, N)
	}
}

func TestWSIntegration_NoToken_401(t *testing.T) {
	hub := ws.NewHub()
	cfg := &config.Config{JWTSecret: "test-secret"}
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}, Hub: hub,
	}))
	defer srv.Close()
	wsURL := strings.Replace(srv.URL, "http", "ws", 1) + "/"
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, http.Header{})
	if err == nil {
		t.Fatal("expected dial to fail without token")
	}
	if resp == nil || resp.StatusCode != 401 {
		t.Errorf("status=%v", resp)
	}
}
