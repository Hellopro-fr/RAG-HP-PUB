package tools

import (
	"context"
	"encoding/json"
	"reflect"
	"sort"
	"testing"

	"github.com/hellopro/mcp-ringover/internal/transport"
)

// scopedCtx returns a ctx with the given allowed user IDs attached, as if the
// gateway had set the X-Ringover-Allowed-User-IDs header.
func scopedCtx(ids ...int) context.Context {
	ctx := context.Background()
	if ids == nil {
		return transport.WithAllowedUserIDsForTest(ctx, nil, false)
	}
	return transport.WithAllowedUserIDsForTest(ctx, ids, true)
}

func TestEffectiveUserIDs_Unrestricted(t *testing.T) {
	// No scope → pass through the caller-supplied filter unchanged.
	ctx := context.Background()

	ids, err := effectiveUserIDs(ctx, "")
	if err != nil || ids != nil {
		t.Errorf("empty, unrestricted: got (%v, %v)", ids, err)
	}
	ids, err = effectiveUserIDs(ctx, "42")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !reflect.DeepEqual(ids, []int{42}) {
		t.Errorf("got %v", ids)
	}
}

func TestEffectiveUserIDs_RestrictedNoCallerFilter(t *testing.T) {
	ctx := scopedCtx(10, 20, 30)
	ids, err := effectiveUserIDs(ctx, "")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	sort.Ints(ids)
	if !reflect.DeepEqual(ids, []int{10, 20, 30}) {
		t.Errorf("got %v", ids)
	}
}

func TestEffectiveUserIDs_RestrictedCallerInSet(t *testing.T) {
	ctx := scopedCtx(10, 20, 30)
	ids, err := effectiveUserIDs(ctx, "20")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !reflect.DeepEqual(ids, []int{20}) {
		t.Errorf("got %v", ids)
	}
}

func TestEffectiveUserIDs_RestrictedCallerOutsideSet(t *testing.T) {
	ctx := scopedCtx(10, 20, 30)
	_, err := effectiveUserIDs(ctx, "99")
	if err == nil {
		t.Fatal("expected access-denied error for user outside scope")
	}
}

func TestEffectiveUserIDs_RestrictedInvalidCaller(t *testing.T) {
	ctx := scopedCtx(10, 20)
	_, err := effectiveUserIDs(ctx, "not-a-number")
	if err == nil {
		t.Fatal("expected error for non-numeric user_id")
	}
}

func TestEffectiveUserIDs_DenyAll(t *testing.T) {
	// Restricted but allowed list is empty → everything is denied.
	ctx := transport.WithAllowedUserIDsForTest(context.Background(), nil, true)
	_, err := effectiveUserIDs(ctx, "")
	if err == nil {
		t.Fatal("expected error for deny-all scope")
	}
}

func TestCheckCallOwnedByAllowed_Unrestricted(t *testing.T) {
	if err := checkCallOwnedByAllowed(context.Background(), 42); err != nil {
		t.Errorf("unrestricted should allow: %v", err)
	}
}

func TestCheckCallOwnedByAllowed_Allowed(t *testing.T) {
	ctx := scopedCtx(10, 20)
	if err := checkCallOwnedByAllowed(ctx, 10); err != nil {
		t.Errorf("expected allowed: %v", err)
	}
}

func TestCheckCallOwnedByAllowed_Denied(t *testing.T) {
	ctx := scopedCtx(10, 20)
	if err := checkCallOwnedByAllowed(ctx, 99); err == nil {
		t.Error("expected denial")
	}
}

func TestCheckCallOwnedByAllowed_UnknownUserID(t *testing.T) {
	// user_id = 0 means "no agent info in the response" → fail closed under scope.
	ctx := scopedCtx(10)
	if err := checkCallOwnedByAllowed(ctx, 0); err == nil {
		t.Error("expected denial when user_id is unknown under scope")
	}
}

func TestEffectiveStatsUserID_Unrestricted(t *testing.T) {
	ctx := context.Background()
	got, err := effectiveStatsUserID(ctx, "")
	if err != nil || got != "" {
		t.Errorf("unrestricted empty: got (%q, %v)", got, err)
	}
	got, err = effectiveStatsUserID(ctx, "42")
	if err != nil || got != "42" {
		t.Errorf("unrestricted caller: got (%q, %v)", got, err)
	}
}

func TestEffectiveStatsUserID_SingleUserScope(t *testing.T) {
	ctx := scopedCtx(42)
	got, err := effectiveStatsUserID(ctx, "")
	if err != nil || got != "42" {
		t.Errorf("single-user scope no caller: got (%q, %v)", got, err)
	}
	got, err = effectiveStatsUserID(ctx, "42")
	if err != nil || got != "42" {
		t.Errorf("single-user scope matching caller: got (%q, %v)", got, err)
	}
}

func TestEffectiveStatsUserID_MultiUserScopeNoCaller(t *testing.T) {
	ctx := scopedCtx(10, 20, 30)
	_, err := effectiveStatsUserID(ctx, "")
	if err == nil {
		t.Fatal("expected error — /stats/team cannot express multi-user scope without caller pick")
	}
}

func TestEffectiveStatsUserID_MultiUserScopeCallerInSet(t *testing.T) {
	ctx := scopedCtx(10, 20, 30)
	got, err := effectiveStatsUserID(ctx, "20")
	if err != nil || got != "20" {
		t.Errorf("multi-user scope caller in set: got (%q, %v)", got, err)
	}
}

func TestEffectiveStatsUserID_CallerOutsideScope(t *testing.T) {
	ctx := scopedCtx(10, 20)
	_, err := effectiveStatsUserID(ctx, "99")
	if err == nil {
		t.Fatal("expected access-denied for caller outside scope")
	}
}

func TestEffectiveStatsUserID_DenyAll(t *testing.T) {
	ctx := transport.WithAllowedUserIDsForTest(context.Background(), nil, true)
	_, err := effectiveStatsUserID(ctx, "")
	if err == nil {
		t.Fatal("expected deny-all error")
	}
}

func TestExtractCallUserID(t *testing.T) {
	// Ringover /calls/{id} returns { call_list: [{ user_id: ..., ... }] }.
	body := json.RawMessage(`{"call_list":[{"cdr_id":"abc","user_id":42}]}`)
	if got := extractCallUserID(body); got != 42 {
		t.Errorf("extractCallUserID = %d, want 42", got)
	}

	// Bare object fallback (some clients strip the envelope).
	body = json.RawMessage(`{"cdr_id":"abc","user_id":17}`)
	if got := extractCallUserID(body); got != 17 {
		t.Errorf("extractCallUserID = %d, want 17", got)
	}

	// Missing → 0.
	body = json.RawMessage(`{"cdr_id":"abc"}`)
	if got := extractCallUserID(body); got != 0 {
		t.Errorf("missing user_id should yield 0, got %d", got)
	}
}
