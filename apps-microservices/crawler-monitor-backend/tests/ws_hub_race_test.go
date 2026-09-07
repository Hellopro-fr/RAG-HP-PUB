package tests

import (
	"fmt"
	"sync"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
)

// TestWSHub_ConcurrentBroadcastUnregister valide (sous -race) que Broadcast et
// Unregister ne peuvent plus se croiser : avant le correctif, Broadcast
// pouvait ecrire dans un canal ferme entre-temps par Unregister
// ("send on closed channel"), panic avalee par le recover() du pub/sub.
func TestWSHub_ConcurrentBroadcastUnregister(t *testing.T) {
	const clients = 32
	const messages = 500

	h := ws.NewHub()
	cs := make([]*ws.Client, clients)
	for i := range cs {
		cs[i] = ws.NewClientForTest()
		h.Register(cs[i])
	}

	// Consommateurs : vident les canaux jusqu'a leur fermeture.
	var consumers sync.WaitGroup
	for _, c := range cs {
		consumers.Add(1)
		go func(c *ws.Client) {
			defer consumers.Done()
			for range c.SendForTest() {
			}
		}(c)
	}

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < messages; i++ {
			h.Broadcast([]byte(fmt.Sprintf(`{"i":%d}`, i)))
		}
	}()
	for _, c := range cs {
		wg.Add(1)
		go func(c *ws.Client) {
			defer wg.Done()
			h.Unregister(c)
			// Double desinscription : doit rester sans effet.
			h.Unregister(c)
		}(c)
	}
	wg.Wait()
	consumers.Wait()

	if h.Count() != 0 {
		t.Errorf("count = %d, want 0", h.Count())
	}
	// Un broadcast apres desinscription totale ne doit pas paniquer.
	h.Broadcast([]byte("after"))
}
