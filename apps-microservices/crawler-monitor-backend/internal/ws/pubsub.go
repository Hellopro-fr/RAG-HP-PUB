package ws

import (
	"context"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"
)

type PubSub struct {
	rdb      *redis.Client
	hub      *Hub
	channels []string
}

func NewPubSub(rdb *redis.Client, hub *Hub, channels ...string) *PubSub {
	return &PubSub{rdb: rdb, hub: hub, channels: channels}
}

func (p *PubSub) Run(ctx context.Context) {
	backoff := time.Second
	const maxBackoff = 30 * time.Second
	for {
		if err := p.runOnce(ctx); err != nil {
			if ctx.Err() != nil {
				return
			}
			slog.Warn("ws.pubsub.disconnect", "err", err, "backoff", backoff)
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return
			}
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
			continue
		}
		return
	}
}

func (p *PubSub) runOnce(ctx context.Context) error {
	sub := p.rdb.Subscribe(ctx, p.channels...)
	defer sub.Close()
	if _, err := sub.Receive(ctx); err != nil {
		return err
	}
	ch := sub.Channel()
	slog.Info("ws.pubsub.subscribed", "channels", p.channels)
	for {
		select {
		case <-ctx.Done():
			return nil
		case msg, ok := <-ch:
			if !ok {
				return nil
			}
			func() {
				defer func() { _ = recover() }()
				p.hub.Broadcast([]byte(msg.Payload))
			}()
		}
	}
}
