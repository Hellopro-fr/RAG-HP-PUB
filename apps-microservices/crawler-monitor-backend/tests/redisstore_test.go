package tests

import (
	"context"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func newMini(t *testing.T) (*redisstore.Client, *miniredis.Miniredis) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)
	c, err := redisstore.New("redis://" + mr.Addr())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c, mr
}

func TestRedisStore_ListJobs(t *testing.T) {
	c, mr := newMini(t)
	mr.Set("crawl_job:abc", `{"id":"abc","status":"running"}`)
	mr.Set("crawl_job:def", `{"id":"def","status":"finished"}`)
	mr.Set("other:key", "ignored")
	jobs, err := c.ListJobs(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 2 {
		t.Errorf("len(jobs) = %d, want 2", len(jobs))
	}
}

func TestRedisStore_GetCapacity(t *testing.T) {
	c, mr := newMini(t)
	mr.Set(redisstore.RunningCountKey, "5")
	mr.Set(redisstore.MaxGlobalKey, "10")
	r, m, err := c.GetCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if r != 5 || m != 10 {
		t.Errorf("running=%d max=%d, want 5,10", r, m)
	}
}

func TestRedisStore_GetJobNotFound(t *testing.T) {
	c, _ := newMini(t)
	_, err := c.GetJob(context.Background(), "nope")
	if err == nil {
		t.Error("expected redis.Nil error")
	}
}
