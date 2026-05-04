package logout

import (
	"context"
	"sync"

	"github.com/hellopro/account-service/internal/db"
)

type EventRepo interface {
	Create(e *db.LogoutEvent) error
	MarkSent(id string) error
	MarkFailed(id, errMsg string) error
}

type Sender interface {
	Deliver(url, secret string, body []byte) DeliveryResult
}

type LogoutJob struct {
	ID           string
	ClientID     string
	UserEmail    string
	SID          string
	WebhookURL   string
	ClientSecret string
	Body         []byte
}

type WorkerConfig struct {
	Workers    int
	BufferSize int
	Deliverer  Sender
	Repo       EventRepo
}

type WorkerPool struct {
	cfg WorkerConfig
	ch  chan LogoutJob
	wg  sync.WaitGroup
}

func NewWorkerPool(cfg WorkerConfig) *WorkerPool {
	if cfg.Workers == 0 {
		cfg.Workers = 4
	}
	if cfg.BufferSize == 0 {
		cfg.BufferSize = 256
	}
	return &WorkerPool{cfg: cfg, ch: make(chan LogoutJob, cfg.BufferSize)}
}

func (p *WorkerPool) Start(ctx context.Context) {
	for i := 0; i < p.cfg.Workers; i++ {
		p.wg.Add(1)
		go p.run(ctx)
	}
}

func (p *WorkerPool) run(ctx context.Context) {
	defer p.wg.Done()
	for {
		select {
		case <-ctx.Done():
			return
		case job, ok := <-p.ch:
			if !ok {
				return
			}
			res := p.cfg.Deliverer.Deliver(job.WebhookURL, job.ClientSecret, job.Body)
			if res.Sent {
				_ = p.cfg.Repo.MarkSent(job.ID)
			} else {
				_ = p.cfg.Repo.MarkFailed(job.ID, res.LastError)
			}
		}
	}
}

// Enqueue is non-blocking: drops the job if the buffer is full. Caller still
// has the persisted logout_events row to retry from.
func (p *WorkerPool) Enqueue(j LogoutJob) bool {
	select {
	case p.ch <- j:
		return true
	default:
		return false
	}
}

func (p *WorkerPool) Wait() {
	p.wg.Wait()
}
