package benchmarks

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

type fakeAudit struct{}

func (f *fakeAudit) Append(_ context.Context, _ map[string]any) error { return nil }

func mintTokBench(secret string) string {
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"role": "admin",
		"exp":  time.Now().Add(time.Hour).Unix(),
	})
	s, _ := tok.SignedString([]byte(secret))
	return s
}

func TestWSBroadcastP99(t *testing.T) {
	if testing.Short() {
		t.Skip("skip bench in short mode")
	}
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
		Config: cfg, RedisStore: rs, AuditStore: &fakeAudit{}, Hub: hub,
	}))
	defer srv.Close()
	wsURL := strings.Replace(srv.URL, "http", "ws", 1) + "/?token=" + mintTokBench("test-secret")

	const N = 50
	const RATE = 50
	const DUR = 5 * time.Second

	type sample struct{ lat time.Duration }
	samplesCh := make(chan sample, 100000)
	var wg sync.WaitGroup
	conns := make([]*websocket.Conn, N)
	for i := 0; i < N; i++ {
		c, _, err := websocket.DefaultDialer.Dial(wsURL, http.Header{})
		if err != nil {
			t.Fatal(err)
		}
		conns[i] = c
		wg.Add(1)
		go func(c *websocket.Conn) {
			defer wg.Done()
			_ = c.SetReadDeadline(time.Now().Add(DUR + 5*time.Second))
			for {
				_, msg, err := c.ReadMessage()
				if err != nil {
					return
				}
				var sentNs int64
				_, _ = fmt.Sscanf(string(msg), `{"sent":%d}`, &sentNs)
				lat := time.Since(time.Unix(0, sentNs))
				select {
				case samplesCh <- sample{lat: lat}:
				default:
				}
			}
		}(conns[i])
	}

	go func() {
		ticker := time.NewTicker(time.Second / RATE)
		defer ticker.Stop()
		end := time.Now().Add(DUR)
		for time.Now().Before(end) {
			<-ticker.C
			rdb.Publish(context.Background(), "crawl_updates",
				fmt.Sprintf(`{"sent":%d}`, time.Now().UnixNano()))
		}
	}()

	time.Sleep(DUR + 2*time.Second)
	for _, c := range conns {
		_ = c.Close()
	}
	close(samplesCh)
	wg.Wait()

	var lat []time.Duration
	for s := range samplesCh {
		lat = append(lat, s.lat)
	}
	if len(lat) == 0 {
		t.Fatal("no samples")
	}
	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	p50 := lat[len(lat)/2]
	p95 := lat[len(lat)*95/100]
	p99 := lat[len(lat)*99/100]
	t.Logf("samples=%d p50=%v p95=%v p99=%v", len(lat), p50, p95, p99)
	if p99 > 100*time.Millisecond {
		t.Errorf("p99=%v, want <= 100ms", p99)
	}
}
