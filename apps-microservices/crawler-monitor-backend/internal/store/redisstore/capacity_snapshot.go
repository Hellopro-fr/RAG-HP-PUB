package redisstore

import (
	"context"
	"encoding/json"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/redis/go-redis/v9"
)

// CapacityRetentionMs is 24 hours.
const CapacityRetentionMs = int64(24 * 60 * 60 * 1000)

// SnapshotCapacity reads running/max from Redis, ZADDs a CapacityPoint to
// capacity:history:zset, and prunes entries older than 24h.
// Mirrors JS snapshotCapacity().
func (c *Client) SnapshotCapacity(ctx context.Context) error {
	running, max, err := c.GetCapacity(ctx)
	if err != nil {
		return err
	}
	now := time.Now().UnixMilli()
	point := systemstats.CapacityPoint{
		Ts:      now,
		Running: running,
		Max:     max,
		Full:    max > 0 && running >= max,
	}
	raw, err := json.Marshal(point)
	if err != nil {
		return err
	}
	if err := c.rdb.ZAdd(ctx, CapacityHistoryKey, redis.Z{Score: float64(now), Member: string(raw)}).Err(); err != nil {
		return err
	}
	_ = c.rdb.ZRemRangeByScore(ctx, CapacityHistoryKey, "0", formatScore(now-CapacityRetentionMs)).Err()
	return nil
}
