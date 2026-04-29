package tests

import (
	"sync"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
)

func TestWSHub_BroadcastReachesAllClients(t *testing.T) {
	h := ws.NewHub()
	clients := make([]*ws.Client, 50)
	for i := range clients {
		clients[i] = ws.NewClientForTest()
		h.Register(clients[i])
	}
	if h.Count() != 50 {
		t.Fatalf("count=%d", h.Count())
	}
	var wg sync.WaitGroup
	wg.Add(50)
	received := make([]int, 50)
	for i, c := range clients {
		go func(i int, c *ws.Client) {
			defer wg.Done()
			deadline := time.After(2 * time.Second)
			select {
			case msg, ok := <-c.SendForTest():
				if ok && string(msg) == "hello" {
					received[i]++
				}
			case <-deadline:
			}
		}(i, c)
	}
	h.Broadcast([]byte("hello"))
	wg.Wait()
	missed := 0
	for _, n := range received {
		if n == 0 {
			missed++
		}
	}
	if missed > 0 {
		t.Errorf("missed: %d/50", missed)
	}
}

func TestWSHub_SlowClientDropped(t *testing.T) {
	h := ws.NewHub()
	c := ws.NewClientForTest()
	h.Register(c)
	for i := 0; i < 257; i++ {
		h.Broadcast([]byte("x"))
	}
	time.Sleep(50 * time.Millisecond)
	if h.Count() != 0 {
		t.Errorf("slow client not dropped, count=%d", h.Count())
	}
}

func TestWSHub_Close(t *testing.T) {
	h := ws.NewHub()
	for i := 0; i < 10; i++ {
		h.Register(ws.NewClientForTest())
	}
	h.Close()
	if h.Count() != 0 {
		t.Errorf("count after Close = %d", h.Count())
	}
}
