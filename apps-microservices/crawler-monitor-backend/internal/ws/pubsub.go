package ws

import (
	"context"
	"encoding/json"
	"log/slog"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

// jobKeyPrefix mirrors redisstore.JobPrefix — local to avoid import cycle.
const jobKeyPrefix = "crawl_job:"

// stringOrNum extracts a string from a map value that may be a string or a number.
func stringOrNum(v any) string {
	switch val := v.(type) {
	case string:
		return val
	case float64:
		if val == float64(int64(val)) {
			return strconv.FormatInt(int64(val), 10)
		}
		return strconv.FormatFloat(val, 'f', -1, 64)
	case int64:
		return strconv.FormatInt(val, 10)
	}
	return ""
}

// jobTTL: jobs expire after 48h of inactivity.
const jobTTL = 48 * time.Hour

// replicaHistoryPrefix and knownReplicasKey mirror redisstore constants.
const replicaHistoryPrefix = "replica:history:"
const knownReplicasKey = "replica:known"

// retentionMs: 1h replica history retention (matches redisstore.RetentionReplicaHistoryMs).
const retentionMs = int64(60 * 60 * 1000)

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
				p.persist(ctx, msg.Payload)
			}()
		}
	}
}

// persist upserts crawl_job:<jobId> and replica:history:<replicaId> from pub/sub messages.
func (p *PubSub) persist(ctx context.Context, payload string) {
	var msg map[string]any
	if err := json.Unmarshal([]byte(payload), &msg); err != nil {
		return
	}
	p.persistJob(ctx, msg)
	p.persistReplica(ctx, msg)
}

// persistJob upserts crawl_job:<jobId> preserving start_time on existing entries.
func (p *PubSub) persistJob(ctx context.Context, msg map[string]any) {
	jobID := stringOrNum(msg["jobId"])
	if jobID == "" {
		return
	}
	key := jobKeyPrefix + jobID

	existing := map[string]any{}
	if raw, err := p.rdb.Get(ctx, key).Result(); err == nil {
		_ = json.Unmarshal([]byte(raw), &existing)
	}

	if _, hasStart := existing["start_time"]; !hasStart {
		if ts, ok := msg["timestamp"].(float64); ok {
			existing["start_time"] = time.UnixMilli(int64(ts)).UTC().Format(time.RFC3339Nano)
		} else {
			existing["start_time"] = time.Now().UTC().Format(time.RFC3339Nano)
		}
	}

	existing["id"] = jobID
	existing["_id"] = jobID
	if v := stringOrNum(msg["domain"]); v != "" {
		existing["domain"] = v
	}
	if v := stringOrNum(msg["status"]); v != "" {
		existing["status"] = v
		if v == "finished" || v == "failed" || v == "archived" {
			if _, hasEnd := existing["end_time"]; !hasEnd {
				existing["end_time"] = time.Now().UTC().Format(time.RFC3339Nano)
			}
		}
	}
	if v := stringOrNum(msg["replicaId"]); v != "" {
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
	if v := stringOrNum(msg["crawlMode"]); v != "" {
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

// persistReplica appends a heartbeat sample to replica:history:<replicaId> (ZSet, TTL 1h).
func (p *PubSub) persistReplica(ctx context.Context, msg map[string]any) {
	replicaID := stringOrNum(msg["replicaId"])
	if replicaID == "" {
		return
	}
	ts := time.Now().UnixMilli()
	if v, ok := msg["timestamp"].(float64); ok {
		ts = int64(v)
	}
	cpu, _ := msg["cpu"].(float64)
	ram, _ := msg["ram"].(float64)
	totalRAM, _ := msg["totalRam"].(float64)
	jobID := stringOrNum(msg["jobId"])

	sample := map[string]any{
		"ts":       ts,
		"cpu":      cpu,
		"ram":      ram,
		"totalRam": totalRAM,
	}
	if jobID != "" {
		sample["jobId"] = jobID
	}
	raw, err := json.Marshal(sample)
	if err != nil {
		return
	}
	key := replicaHistoryPrefix + replicaID
	minScore := strconv.FormatInt(ts-retentionMs, 10)
	_ = p.rdb.ZAdd(ctx, key, redis.Z{Score: float64(ts), Member: string(raw)}).Err()
	_ = p.rdb.ZRemRangeByScore(ctx, key, "0", minScore).Err()
	_ = p.rdb.SAdd(ctx, knownReplicasKey, replicaID).Err()
}
