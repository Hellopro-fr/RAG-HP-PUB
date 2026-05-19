package logout

import (
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"

	"account-service/internal/db"
)

type captureRepo struct {
	mu      sync.Mutex
	created []db.LogoutEvent
}

func (c *captureRepo) Create(e *db.LogoutEvent) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.created = append(c.created, *e)
	return nil
}
func (c *captureRepo) MarkSent(id string) error           { return nil }
func (c *captureRepo) MarkFailed(id, errMsg string) error { return nil }

type fakeDecrypter struct{}

func (fakeDecrypter) Decrypt(in []byte) ([]byte, error) {
	return []byte(strings.TrimPrefix(string(in), "ENC:")), nil
}

type capturePool struct {
	mu   sync.Mutex
	jobs []LogoutJob
}

func (c *capturePool) Enqueue(j LogoutJob) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.jobs = append(c.jobs, j)
	return true
}

func TestBroadcastSendsToActiveClients(t *testing.T) {
	repo := &captureRepo{}
	pool := &capturePool{}

	clients := []db.OAuth2Client{
		{ClientID: "x1", ClientSecretEnc: []byte("ENC:s1"), LogoutWebhookURL: "https://x1/lo"},
		{ClientID: "x2", ClientSecretEnc: []byte("ENC:s2"), LogoutWebhookURL: ""},
		{ClientID: "x3", ClientSecretEnc: []byte("ENC:s3"), LogoutWebhookURL: "https://x3/lo"},
	}
	b := NewBroadcaster(BroadcasterDeps{
		Decrypter: fakeDecrypter{},
		Repo:      repo,
		Pool:      pool,
		Issuer:    "https://account.test",
	})
	b.Broadcast("a@x", "sid1", clients)

	if len(pool.jobs) != 2 {
		t.Fatalf("jobs=%d (want 2 active webhooks)", len(pool.jobs))
	}
	if len(repo.created) != 2 {
		t.Fatalf("logout_events=%d", len(repo.created))
	}
	for _, j := range pool.jobs {
		var body map[string]interface{}
		_ = json.Unmarshal(j.Body, &body)
		if body["sub"] != "a@x" {
			t.Errorf("sub=%v", body["sub"])
		}
		if body["sid"] != "sid1" {
			t.Errorf("sid=%v", body["sid"])
		}
		iat, _ := body["iat"].(float64)
		if int64(iat) > time.Now().Unix() {
			t.Errorf("iat in future")
		}
	}
}
