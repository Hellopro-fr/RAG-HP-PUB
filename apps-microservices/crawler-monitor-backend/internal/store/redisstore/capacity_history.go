package redisstore

import (
	"context"
	"encoding/json"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/redis/go-redis/v9"
)

// ReadCapacityHistory returns capacity history points within [now-windowMs, now].
// Mirrors JS readCapacityHistory(client, windowMs).
func (c *Client) ReadCapacityHistory(ctx context.Context, windowMs int64) ([]systemstats.CapacityPoint, error) {
	now := time.Now().UnixMilli()
	min := now - windowMs
	strs, err := c.rdb.ZRangeByScore(ctx, CapacityHistoryKey, &redis.ZRangeBy{
		Min: formatScore(min),
		Max: "+inf",
	}).Result()
	if err != nil {
		return nil, err
	}
	out := make([]systemstats.CapacityPoint, 0, len(strs))
	for _, s := range strs {
		var p systemstats.CapacityPoint
		if err := json.Unmarshal([]byte(s), &p); err != nil {
			continue
		}
		out = append(out, p)
	}
	return out, nil
}
