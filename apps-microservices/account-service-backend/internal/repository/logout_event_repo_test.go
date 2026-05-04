//go:build integration

package repository

import (
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
)

func TestLogoutEventEnqueueAndPickPending(t *testing.T) {
	g := setupTestDB(t)
	r := NewLogoutEventRepo(g)
	ev := &db.LogoutEvent{
		ID:            uuid.New().String(),
		ClientID:      "c",
		UserEmail:     "u@x",
		SID:           "sid",
		WebhookURL:    "https://x",
		Status:        "pending",
		NextAttemptAt: time.Now(),
	}
	if err := r.Create(ev); err != nil {
		t.Fatalf("Create: %v", err)
	}
	pending, err := r.PickPending(10)
	if err != nil {
		t.Fatalf("PickPending: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("len=%d", len(pending))
	}
	if err := r.MarkSent(pending[0].ID); err != nil {
		t.Fatalf("MarkSent: %v", err)
	}
	again, _ := r.PickPending(10)
	if len(again) != 0 {
		t.Fatalf("sent row picked again")
	}
}
