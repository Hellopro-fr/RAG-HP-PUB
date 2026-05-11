package api

import (
	"context"
	"testing"
)

// TestResolveLeexiFilterForCreate_NoneMode locks in the unrestricted-mode
// contract: a nil filter (or an explicit "none" mode) returns mode="none"
// with no UUID columns and no error. This protects the existing modes from
// regression as new modes (e.g. "self") are added to the validator.
func TestResolveLeexiFilterForCreate_NoneMode(t *testing.T) {
	mode, users, teams, err := resolveLeexiFilterForCreate(context.Background(), nil, nil, "", false)
	if err != nil {
		t.Fatalf("unexpected error for nil filter: %v", err)
	}
	if mode != LeexiFilterModeNone {
		t.Fatalf("expected mode=none for nil filter, got %q", mode)
	}
	if users != nil || teams != nil {
		t.Fatalf("expected nil UUID columns for none mode, got users=%v teams=%v", users, teams)
	}

	dto := &LeexiFilterDTO{Mode: LeexiFilterModeNone}
	mode, users, teams, err = resolveLeexiFilterForCreate(context.Background(), nil, dto, "", false)
	if err != nil {
		t.Fatalf("unexpected error for explicit none: %v", err)
	}
	if mode != LeexiFilterModeNone {
		t.Fatalf("expected mode=none, got %q", mode)
	}
	if users != nil || teams != nil {
		t.Fatalf("expected nil UUID columns for none mode, got users=%v teams=%v", users, teams)
	}
}

func TestResolveLeexiFilterForCreate_InvalidMode(t *testing.T) {
	dto := &LeexiFilterDTO{Mode: "bogus"}
	_, _, _, err := resolveLeexiFilterForCreate(context.Background(), nil, dto, "", false)
	if err == nil {
		t.Fatalf("expected error for invalid mode, got nil")
	}
}
