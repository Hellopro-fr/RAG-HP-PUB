package logout

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

type fakeRepo struct {
	mu      sync.Mutex
	created []db.LogoutEvent
	sent    map[string]bool
	failed  map[string]string
}

func (f *fakeRepo) Create(e *db.LogoutEvent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.created = append(f.created, *e)
	return nil
}
func (f *fakeRepo) MarkSent(id string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.sent == nil {
		f.sent = map[string]bool{}
	}
	f.sent[id] = true
	return nil
}
func (f *fakeRepo) MarkFailed(id, errMsg string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failed == nil {
		f.failed = map[string]string{}
	}
	f.failed[id] = errMsg
	return nil
}

type fakeDeliverer struct {
	calls int32
	ok    bool
}

func (f *fakeDeliverer) Deliver(url, secret string, body []byte) DeliveryResult {
	atomic.AddInt32(&f.calls, 1)
	return DeliveryResult{Sent: f.ok, Attempts: 1, LastError: "x"}
}

func TestWorkerPool_DispatchesAndMarks(t *testing.T) {
	repo := &fakeRepo{}
	deliv := &fakeDeliverer{ok: true}
	pool := NewWorkerPool(WorkerConfig{
		Workers:    2,
		BufferSize: 10,
		Deliverer:  deliv,
		Repo:       repo,
	})
	ctx, cancel := context.WithCancel(context.Background())
	pool.Start(ctx)

	for i := 0; i < 5; i++ {
		pool.Enqueue(LogoutJob{
			ID:           "id-" + string(rune('a'+i)),
			ClientID:     "x",
			UserEmail:    "a@x",
			SID:          "sid",
			WebhookURL:   "https://x",
			ClientSecret: "secret",
			Body:         []byte(`{}`),
		})
	}

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		repo.mu.Lock()
		ok := len(repo.sent) == 5
		repo.mu.Unlock()
		if ok {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	cancel()
	pool.Wait()
	if int(deliv.calls) != 5 {
		t.Fatalf("calls=%d", deliv.calls)
	}
	if len(repo.sent) != 5 {
		t.Fatalf("sent=%d", len(repo.sent))
	}
}
