package logout

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"account-service/internal/db"
)

type Decrypter interface {
	Decrypt(in []byte) ([]byte, error)
}

type Enqueuer interface {
	Enqueue(LogoutJob) bool
}

type BroadcasterDeps struct {
	Decrypter Decrypter
	Repo      EventRepo
	Pool      Enqueuer
	Issuer    string
}

type Broadcaster struct {
	deps BroadcasterDeps
}

func NewBroadcaster(d BroadcasterDeps) *Broadcaster {
	return &Broadcaster{deps: d}
}

// Broadcast sends a back-channel logout event to every client in the slice
// that has a non-empty logout_webhook_url. Each gets its own logout_events row
// (persistence) and is enqueued onto the worker pool (delivery).
func (b *Broadcaster) Broadcast(userEmail, sid string, clients []db.OAuth2Client) {
	body := map[string]interface{}{
		"iss":    b.deps.Issuer,
		"sub":    userEmail,
		"sid":    sid,
		"iat":    time.Now().Unix(),
		"events": map[string]interface{}{"http://schemas.openid.net/event/backchannel-logout": map[string]interface{}{}},
	}
	bytes, _ := json.Marshal(body)

	for _, c := range clients {
		if c.LogoutWebhookURL == "" {
			continue
		}
		secret, err := b.deps.Decrypter.Decrypt(c.ClientSecretEnc)
		if err != nil {
			continue
		}
		ev := &db.LogoutEvent{
			ID:            uuid.New().String(),
			ClientID:      c.ClientID,
			UserEmail:     userEmail,
			SID:           sid,
			WebhookURL:    c.LogoutWebhookURL,
			Status:        "pending",
			NextAttemptAt: time.Now(),
		}
		if err := b.deps.Repo.Create(ev); err != nil {
			continue
		}
		b.deps.Pool.Enqueue(LogoutJob{
			ID:           ev.ID,
			ClientID:     c.ClientID,
			UserEmail:    userEmail,
			SID:          sid,
			WebhookURL:   c.LogoutWebhookURL,
			ClientSecret: string(secret),
			Body:         bytes,
		})
	}
}
