package redisstore

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/redis/go-redis/v9"
)

type RawJob map[string]any

func (c *Client) ListJobs(ctx context.Context) ([]RawJob, error) {
	keys, err := c.rdb.Keys(ctx, JobPrefix+"*").Result()
	if err != nil {
		return nil, err
	}
	out := make([]RawJob, 0, len(keys))
	for _, k := range keys {
		raw, err := c.rdb.Get(ctx, k).Result()
		if err == redis.Nil {
			continue
		}
		if err != nil {
			return nil, err
		}
		var j RawJob
		if err := json.Unmarshal([]byte(raw), &j); err != nil {
			continue
		}
		j["_redisKey"] = k
		j["_id"] = strings.TrimPrefix(k, JobPrefix)
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
	j["_id"] = id
	return j, nil
}
