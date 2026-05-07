package cache

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func newClient(t *testing.T) (*Cache, *miniredis.Miniredis) {
	t.Helper()
	mr, err := miniredis.Run()
	require.NoError(t, err)
	t.Cleanup(mr.Close)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	return New(rdb), mr
}

func TestSetGetJSON(t *testing.T) {
	c, _ := newClient(t)
	ctx := context.Background()

	require.NoError(t, c.SetJSON(ctx, "k", map[string]any{"a": 1}, 5*time.Second))

	var out map[string]any
	found, err := c.GetJSON(ctx, "k", &out)
	require.NoError(t, err)
	require.True(t, found)
	require.EqualValues(t, 1, out["a"])
}

func TestGetJSONMissing(t *testing.T) {
	c, _ := newClient(t)
	var out map[string]any
	found, err := c.GetJSON(context.Background(), "missing", &out)
	require.NoError(t, err)
	require.False(t, found)
}

func TestDelete(t *testing.T) {
	c, _ := newClient(t)
	ctx := context.Background()
	require.NoError(t, c.SetJSON(ctx, "k", "v", time.Minute))
	require.NoError(t, c.Delete(ctx, "k"))
	var out string
	found, _ := c.GetJSON(ctx, "k", &out)
	require.False(t, found)
}
