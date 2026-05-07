package api

import (
	"context"
	"testing"
)

func TestResolveLeexiFilterForCreate_SelfMode(t *testing.T) {
	dto := &LeexiFilterDTO{Mode: LeexiFilterModeSelf}
	mode, users, teams, err := resolveLeexiFilterForCreate(context.Background(), nil, dto, "")
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
	mode, users, teams, err := resolveRingoverFilterForCreate(context.Background(), nil, dto, "")
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
