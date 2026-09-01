package tests

import (
	"context"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
)

// TestWSPubSub_IdleResubscribesWhenCrawlsRunning : une connexion subscriber a
// demi-morte ne ferme pas le canal go-redis, donc Run ne se reabonne jamais et
// le dashboard reste muet. Le watchdog doit reconstruire l'abonnement des que
// des crawls tournent sans qu'aucun heartbeat n'arrive.
func TestWSPubSub_IdleResubscribesWhenCrawlsRunning(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	mr.Set(redisstore.RunningCountKey, "2")
	rs, _ := redisstore.New("redis://" + mr.Addr())
	defer rs.Close()

	hub := ws.NewHub()
	defer hub.Close()
	c := ws.NewClientForTest()
	hub.Register(c)

	ps := ws.NewPubSub(rs, hub, "crawler:heartbeat")
	ps.SetIdleTimeoutForTest(200 * time.Millisecond)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)

	deadline := time.Now().Add(10 * time.Second)
	for ps.IdleResubscribesForTest() == 0 {
		if time.Now().After(deadline) {
			t.Fatal("aucun reabonnement declenche malgre le silence")
		}
		time.Sleep(10 * time.Millisecond)
	}

	// Le nouvel abonnement doit etre fonctionnel : on publie jusqu'a
	// reception plutot que de parier sur un delai.
	deadline = time.Now().Add(10 * time.Second)
	for {
		mr.Publish("crawler:heartbeat", `{"type":"heartbeat","replicaId":"r1"}`)
		select {
		case <-c.SendForTest():
			return
		case <-time.After(20 * time.Millisecond):
		}
		if time.Now().After(deadline) {
			t.Fatal("plus aucun message diffuse apres le reabonnement")
		}
	}
}

// TestWSPubSub_IdleKeepsSubscriptionWhenNoCrawlRunning : sans crawl actif, le
// silence est normal — reabonner en boucle ne ferait que churner Redis.
func TestWSPubSub_IdleKeepsSubscriptionWhenNoCrawlRunning(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	mr.Set(redisstore.RunningCountKey, "0")
	rs, _ := redisstore.New("redis://" + mr.Addr())
	defer rs.Close()

	hub := ws.NewHub()
	defer hub.Close()
	ps := ws.NewPubSub(rs, hub, "crawler:heartbeat")
	ps.SetIdleTimeoutForTest(100 * time.Millisecond)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)
	waitSubscribed(t, mr, "crawler:heartbeat")

	time.Sleep(500 * time.Millisecond)
	if n := ps.IdleResubscribesForTest(); n != 0 {
		t.Errorf("reabonnements = %d, want 0 (aucun crawl actif)", n)
	}
}
