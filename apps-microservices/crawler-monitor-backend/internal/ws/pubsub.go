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

// jobPerfPrefix and jobPerfRetentionMs mirror redisstore constants.
const jobPerfPrefix = "job:perf:"
const jobPerfRetentionMs = int64(7 * 24 * 60 * 60 * 1000) // 7 days

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
				p.broadcastTransformed(msg.Payload)
				p.persistAndNotify(ctx, msg.Payload)
			}()
		}
	}
}

// broadcastTransformed converts a raw Redis pub/sub heartbeat into the
// replica_heartbeat envelope the React frontend expects:
//
//	{ type: "replica_heartbeat", data: { replicaId, cpu, ram, … } }
//
// job_update events are NOT sent here — they are emitted by persistAndNotify
// only when a job's status actually changes. Sending job_update on every
// heartbeat caused a request storm (React Query invalidated 6+ endpoints
// every 2s per replica).
func (p *PubSub) broadcastTransformed(payload string) {
	var raw map[string]any
	if err := json.Unmarshal([]byte(payload), &raw); err != nil {
		p.hub.Broadcast([]byte(payload))
		return
	}

	msgType, _ := raw["type"].(string)
	if msgType != "heartbeat" {
		p.hub.Broadcast([]byte(payload))
		return
	}

	replicaEnvelope := map[string]any{
		"type": "replica_heartbeat",
		"data": raw,
	}
	if b, err := json.Marshal(replicaEnvelope); err == nil {
		p.hub.Broadcast(b)
	}
}

// emitJobUpdate sends a { type: "job_update", crawl_id } event to all
// connected WebSocket clients, triggering React Query cache invalidation.
func (p *PubSub) emitJobUpdate(jobID string) {
	envelope := map[string]any{
		"type":     "job_update",
		"crawl_id": jobID,
	}
	if b, err := json.Marshal(envelope); err == nil {
		p.hub.Broadcast(b)
	}
}

// persistAndNotify upserts job + replica data and emits job_update only on real changes.
func (p *PubSub) persistAndNotify(ctx context.Context, payload string) {
	var msg map[string]any
	if err := json.Unmarshal([]byte(payload), &msg); err != nil {
		return
	}
	p.persistJob(ctx, msg)
	p.persistReplica(ctx, msg)
	p.persistJobPerf(ctx, msg)
}

// persistJob upserts crawl_job:<jobId> preserving start_time on existing entries.
// Emits a job_update WS event when a new job appears or a job's status changes.
func (p *PubSub) persistJob(ctx context.Context, msg map[string]any) {
	jobID := stringOrNum(msg["jobId"])
	if jobID == "" {
		return
	}
	key := jobKeyPrefix + jobID

	existing := map[string]any{}
	isNewJob := true
	if raw, err := p.rdb.Get(ctx, key).Result(); err == nil {
		_ = json.Unmarshal([]byte(raw), &existing)
		isNewJob = false
	}

	oldStatus, _ := existing["status"].(string)

	if _, hasStart := existing["start_time"]; !hasStart {
		if ts, ok := msg["timestamp"].(float64); ok {
			existing["start_time"] = time.UnixMilli(int64(ts)).UTC().Format(time.RFC3339Nano)
		} else {
			existing["start_time"] = time.Now().UTC().Format(time.RFC3339Nano)
		}
	}

	existing["id"] = jobID
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

	// Emit job_update only when the job is new or its status changed.
	newStatus, _ := existing["status"].(string)
	if isNewJob || (newStatus != "" && newStatus != oldStatus) {
		p.emitJobUpdate(jobID)
	}
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

// persistJobPerf appends a perf sample to job:perf:<jobId> (ZSet, score=ts, 7d TTL).
// Member shape: {ts, cpu, ram, totalRam, replicaId, jobId} — matches Express persistJobPerf
// so the existing computeCapacityPlanning loader can decode it without changes.
func (p *PubSub) persistJobPerf(ctx context.Context, msg map[string]any) {
	jobID := stringOrNum(msg["jobId"])
	if jobID == "" {
		return
	}
	replicaID := stringOrNum(msg["replicaId"])
	ts := time.Now().UnixMilli()
	if v, ok := msg["timestamp"].(float64); ok {
		ts = int64(v)
	}
	cpu, _ := msg["cpu"].(float64)
	ram, _ := msg["ram"].(float64)
	totalRAM, _ := msg["totalRam"].(float64)

	sample := map[string]any{
		"ts":       ts,
		"cpu":      cpu,
		"ram":      ram,
		"totalRam": totalRAM,
		"jobId":    jobID,
	}
	if replicaID != "" {
		sample["replicaId"] = replicaID
	}
	raw, err := json.Marshal(sample)
	if err != nil {
		return
	}
	key := jobPerfPrefix + jobID
	minScore := strconv.FormatInt(ts-jobPerfRetentionMs, 10)
	_ = p.rdb.ZAdd(ctx, key, redis.Z{Score: float64(ts), Member: string(raw)}).Err()
	_ = p.rdb.ZRemRangeByScore(ctx, key, "0", minScore).Err()
	_ = p.rdb.Expire(ctx, key, time.Duration(jobPerfRetentionMs)*time.Millisecond).Err()
}
