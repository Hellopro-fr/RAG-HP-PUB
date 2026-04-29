package ws

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"
)

// jobKeyPrefix mirrors redisstore.JobPrefix — kept local to avoid import cycle.
const jobKeyPrefix = "crawl_job:"

// jobTTL: jobs expire after 48h of inactivity (auto-cleanup for stale entries).
const jobTTL = 48 * time.Hour

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
				p.persistJob(ctx, msg.Payload)
			}()
		}
	}
}

// persistJob upserts crawl_job:<jobId> in Redis from any pub/sub message that carries a jobId.
// Preserves start_time on existing entries; sets it from timestamp on first sight.
func (p *PubSub) persistJob(ctx context.Context, payload string) {
	var msg map[string]any
	if err := json.Unmarshal([]byte(payload), &msg); err != nil {
		return
	}
	jobID, _ := msg["jobId"].(string)
	if jobID == "" {
		return
	}
	key := jobKeyPrefix + jobID

	// Load existing entry to preserve immutable fields (start_time, crawl_mode…).
	existing := map[string]any{}
	if raw, err := p.rdb.Get(ctx, key).Result(); err == nil {
		_ = json.Unmarshal([]byte(raw), &existing)
	}

	// Preserve or initialise start_time.
	if _, hasStart := existing["start_time"]; !hasStart {
		if ts, ok := msg["timestamp"].(float64); ok {
			existing["start_time"] = time.UnixMilli(int64(ts)).UTC().Format(time.RFC3339Nano)
		} else {
			existing["start_time"] = time.Now().UTC().Format(time.RFC3339Nano)
		}
	}

	// Mutable fields — always update from incoming message.
	existing["id"] = jobID
	existing["_id"] = jobID
	if v, ok := msg["domain"].(string); ok && v != "" {
		existing["domain"] = v
	}
	if v, ok := msg["status"].(string); ok && v != "" {
		existing["status"] = v
		// Record end_time when job transitions to a terminal state.
		terminal := v == "finished" || v == "failed" || v == "archived"
		if terminal {
			if _, hasEnd := existing["end_time"]; !hasEnd {
				existing["end_time"] = time.Now().UTC().Format(time.RFC3339Nano)
			}
		}
	}
	if v, ok := msg["replicaId"].(string); ok && v != "" {
		existing["replica_id"] = v
	}
	if v, ok := msg["cpu"].(float64); ok {
		existing["cpu"] = v
	}
	if v, ok := msg["ram"].(float64); ok {
		existing["ram"] = v
	}
	if v, ok := msg["totalRam"].(float64); ok {
		existing["total_ram"] = v
	}
	if v, ok := msg["crawlMode"].(string); ok && v != "" {
		existing["crawl_mode"] = v
	}
	if v, ok := msg["oomRestartCount"].(float64); ok {
		existing["oom_restart_count"] = int(v)
	}

	out, err := json.Marshal(existing)
	if err != nil {
		return
	}
	_ = p.rdb.Set(ctx, key, string(out), jobTTL).Err()
}
