package redisstore

import (
	"context"
	"encoding/json"
	"strings"
)

type RawJob map[string]any

func (c *Client) ListJobs(ctx context.Context) ([]RawJob, error) {
	var keys []string
	var cursor uint64
	// COUNT=10000 keeps SCAN non-blocking on large keyspaces while avoiding
	// excessive round-trips for typical (~few thousand) job populations.
	for {
		batch, next, err := c.rdb.Scan(ctx, cursor, JobPrefix+"*", 10000).Result()
		if err != nil {
			return nil, err
		}
		keys = append(keys, batch...)
		cursor = next
		if cursor == 0 {
			break
		}
	}
	if len(keys) == 0 {
		return []RawJob{}, nil
	}
	out := make([]RawJob, 0, len(keys))
	// MGET fetches all values in a single round trip instead of N individual GETs.
	vals, err := c.rdb.MGet(ctx, keys...).Result()
	if err != nil {
		return nil, err
	}
	for i, v := range vals {
		s, ok := v.(string)
		if !ok || s == "" {
			continue
		}
		var j RawJob
		if err := json.Unmarshal([]byte(s), &j); err != nil {
			continue
		}
		j["_redisKey"] = keys[i]
		j["id"] = strings.TrimPrefix(keys[i], JobPrefix)
		out = append(out, j)
	}
	return out, nil
}

func (c *Client) GetJob(ctx context.Context, id string) (RawJob, error) {
	raw, err := c.rdb.Get(ctx, JobPrefix+id).Result()
	if err != nil {
		return nil, err
	}
	var j RawJob
	if err := json.Unmarshal([]byte(raw), &j); err != nil {
		return nil, err
	}
	j["id"] = id
	return j, nil
}
