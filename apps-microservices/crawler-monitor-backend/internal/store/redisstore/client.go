package redisstore

import (
	"context"
	"strconv"

	"github.com/redis/go-redis/v9"
)

type Client struct{ rdb *redis.Client }

func New(redisURL string) (*Client, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &Client{rdb: redis.NewClient(opts)}, nil
}

func (c *Client) Close() error       { return c.rdb.Close() }
func (c *Client) Raw() *redis.Client { return c.rdb }

func (c *Client) GetCapacity(ctx context.Context) (running, max int, err error) {
	rStr, err := c.rdb.Get(ctx, RunningCountKey).Result()
	if err != nil && err != redis.Nil {
		return 0, 0, err
	}
	mStr, err := c.rdb.Get(ctx, MaxGlobalKey).Result()
	if err != nil && err != redis.Nil {
		return 0, 0, err
	}
	running, _ = strconv.Atoi(rStr)
	max, _ = strconv.Atoi(mStr)
	return running, max, nil
}

func (c *Client) Subscribe(ctx context.Context, channels ...string) *redis.PubSub {
	return c.rdb.Subscribe(ctx, channels...)
}
