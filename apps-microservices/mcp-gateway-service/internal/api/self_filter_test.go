package api

import (
	"context"
	"testing"
)

func TestResolveLeexiFilterForCreate_SelfMode(t *testing.T) {
	dto := &LeexiFilterDTO{Mode: LeexiFilterModeSelf}
	mode, users, teams, err := resolveLeexiFilterForCreate(context.Background(), nil, dto, "", true /* OAuth2 path */)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if mode != LeexiFilterModeSelf {
		t.Fatalf("expected mode=self, got %q", mode)
	}
	if users != nil || teams != nil {
		t.Fatalf("expected nil UUID columns for self mode, got users=%v teams=%v", users, teams)
	}
}

func TestResolveRingoverFilterForCreate_SelfMode(t *testing.T) {
	dto := &RingoverFilterDTO{Mode: RingoverFilterModeSelf}
	mode, users, teams, err := resolveRingoverFilterForCreate(context.Background(), nil, dto, "", true /* OAuth2 path */)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if mode != RingoverFilterModeSelf {
		t.Fatalf("expected mode=self, got %q", mode)
	}
	if users != nil || teams != nil {
		t.Fatalf("expected nil ID columns for self mode, got users=%v teams=%v", users, teams)
	}
}

// TestResolveLeexiFilterForCreate_SelfMode_RejectedForScopeToken locks in the
// defense-in-depth contract: "self" mode is meaningful only for OAuth2 clients
// (where the JWT carries an end-user email claim). The scope-token API path
// must reject it at the validator with a clear error rather than persisting a
// row that would deny-all at runtime.
func TestResolveLeexiFilterForCreate_SelfMode_RejectedForScopeToken(t *testing.T) {
	dto := &LeexiFilterDTO{Mode: LeexiFilterModeSelf}
	_, _, _, err := resolveLeexiFilterForCreate(context.Background(), nil, dto, "", false /* scope-token path */)
	if err == nil {
		t.Fatal("expected error rejecting self mode on scope-token path, got nil")
	}
}

func TestResolveRingoverFilterForCreate_SelfMode_RejectedForScopeToken(t *testing.T) {
	dto := &RingoverFilterDTO{Mode: RingoverFilterModeSelf}
	_, _, _, err := resolveRingoverFilterForCreate(context.Background(), nil, dto, "", false /* scope-token path */)
	if err == nil {
		t.Fatal("expected error rejecting self mode on scope-token path, got nil")
	}
}
