package tools

import (
	"context"
	"encoding/json"
	"reflect"
	"testing"

	"github.com/hellopro/mcp-leexi/internal/transport"
)

// scopedCtx returns a ctx with the given allowed participant UUIDs attached,
// as if the gateway had set the X-Leexi-Allowed-Participants header.
func scopedCtx(uuids ...string) context.Context {
	ctx := context.Background()
	if uuids == nil {
		return transport.WithAllowedParticipantsForTest(ctx, nil, false)
	}
	return transport.WithAllowedParticipantsForTest(ctx, uuids, true)
}

// ── effectiveParticipantUUIDs ────────────────────────────────────────────────

func TestEffectiveParticipantUUIDs_Unrestricted(t *testing.T) {
	ctx := context.Background()

	uuids, err := effectiveParticipantUUIDs(ctx, "")
	if err != nil || uuids != nil {
		t.Errorf("empty, unrestricted: got (%v, %v)", uuids, err)
	}

	uuids, err = effectiveParticipantUUIDs(ctx, "uuid-x")
	if err != nil || !reflect.DeepEqual(uuids, []string{"uuid-x"}) {
		t.Errorf("caller, unrestricted: got (%v, %v)", uuids, err)
	}
}

func TestEffectiveParticipantUUIDs_RestrictedNoCaller(t *testing.T) {
	ctx := scopedCtx("uuid-a", "uuid-b")
	uuids, err := effectiveParticipantUUIDs(ctx, "")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !reflect.DeepEqual(uuids, []string{"uuid-a", "uuid-b"}) {
		t.Errorf("got %v", uuids)
	}
}

func TestEffectiveParticipantUUIDs_RestrictedCallerInSet(t *testing.T) {
	ctx := scopedCtx("uuid-a", "uuid-b")
	uuids, err := effectiveParticipantUUIDs(ctx, "uuid-b")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !reflect.DeepEqual(uuids, []string{"uuid-b"}) {
		t.Errorf("got %v", uuids)
	}
}

func TestEffectiveParticipantUUIDs_RestrictedCallerOutsideSet(t *testing.T) {
	ctx := scopedCtx("uuid-a", "uuid-b")
	_, err := effectiveParticipantUUIDs(ctx, "uuid-z")
	if err == nil {
		t.Fatal("expected access-denied for caller outside scope")
	}
}

func TestEffectiveParticipantUUIDs_DenyAll(t *testing.T) {
	// Restricted=true with empty allowed list → deny-all.
	ctx := transport.WithAllowedParticipantsForTest(context.Background(), nil, true)
	_, err := effectiveParticipantUUIDs(ctx, "")
	if err == nil {
		t.Fatal("expected deny-all error")
	}
	_, err = effectiveParticipantUUIDs(ctx, "uuid-a")
	if err == nil {
		t.Fatal("expected deny-all error even with caller-supplied uuid")
	}
}

// ── checkCallParticipantAllowed ──────────────────────────────────────────────

func callWithSpeakers(uuids ...string) map[string]json.RawMessage {
	type speaker struct {
		UUID string `json:"uuid"`
	}
	speakers := make([]speaker, len(uuids))
	for i, u := range uuids {
		speakers[i] = speaker{UUID: u}
	}
	raw, _ := json.Marshal(speakers)
	return map[string]json.RawMessage{"speakers": raw}
}

func callWithOwnerUUID(uuid string) map[string]json.RawMessage {
	raw, _ := json.Marshal(uuid)
	return map[string]json.RawMessage{"owner_uuid": raw}
}

func TestCheckCallParticipantAllowed_Unrestricted(t *testing.T) {
	call := callWithSpeakers("uuid-x")
	if err := checkCallParticipantAllowed(context.Background(), call); err != nil {
		t.Errorf("unrestricted should allow: %v", err)
	}
}

func TestCheckCallParticipantAllowed_SpeakersMatch(t *testing.T) {
	ctx := scopedCtx("uuid-a", "uuid-b")
	call := callWithSpeakers("uuid-x", "uuid-b")
	if err := checkCallParticipantAllowed(ctx, call); err != nil {
		t.Errorf("expected allowed (intersect on uuid-b): %v", err)
	}
}

func TestCheckCallParticipantAllowed_SpeakersNoMatch(t *testing.T) {
	ctx := scopedCtx("uuid-a", "uuid-b")
	call := callWithSpeakers("uuid-x", "uuid-y")
	if err := checkCallParticipantAllowed(ctx, call); err == nil {
		t.Error("expected denial when no speaker is in scope")
	}
}

func TestCheckCallParticipantAllowed_OwnerFallback(t *testing.T) {
	ctx := scopedCtx("uuid-a")
	call := callWithOwnerUUID("uuid-a")
	if err := checkCallParticipantAllowed(ctx, call); err != nil {
		t.Errorf("expected allowed via owner_uuid: %v", err)
	}
}

func TestCheckCallParticipantAllowed_OwnerDenied(t *testing.T) {
	ctx := scopedCtx("uuid-a")
	call := callWithOwnerUUID("uuid-z")
	if err := checkCallParticipantAllowed(ctx, call); err == nil {
		t.Error("expected denial when owner not in scope")
	}
}

func TestCheckCallParticipantAllowed_UnknownParticipants(t *testing.T) {
	// No speakers, no owner → fail closed under scope.
	ctx := scopedCtx("uuid-a")
	call := map[string]json.RawMessage{}
	if err := checkCallParticipantAllowed(ctx, call); err == nil {
		t.Error("expected denial when participants cannot be determined")
	}
}

func TestCheckCallParticipantAllowed_DenyAll(t *testing.T) {
	ctx := transport.WithAllowedParticipantsForTest(context.Background(), nil, true)
	call := callWithSpeakers("uuid-anything")
	if err := checkCallParticipantAllowed(ctx, call); err == nil {
		t.Error("expected deny-all error")
	}
}

// ── extractors ───────────────────────────────────────────────────────────────

func TestExtractSpeakerUUIDs(t *testing.T) {
	call := callWithSpeakers("uuid-a", "uuid-b")
	got := extractSpeakerUUIDs(call)
	if !reflect.DeepEqual(got, []string{"uuid-a", "uuid-b"}) {
		t.Errorf("got %v", got)
	}

	// Empty / null speakers array.
	call = map[string]json.RawMessage{"speakers": json.RawMessage(`null`)}
	if got := extractSpeakerUUIDs(call); got != nil {
		t.Errorf("null speakers should yield nil, got %v", got)
	}
}

func TestExtractOwnerUUID(t *testing.T) {
	call := callWithOwnerUUID("uuid-a")
	if got := extractOwnerUUID(call); got != "uuid-a" {
		t.Errorf("got %q", got)
	}

	// Nested {"owner": {"uuid": "..."}}.
	call = map[string]json.RawMessage{"owner": json.RawMessage(`{"uuid":"uuid-b"}`)}
	if got := extractOwnerUUID(call); got != "uuid-b" {
		t.Errorf("nested owner: got %q", got)
	}

	// Nested {"user": {"uuid": "..."}}.
	call = map[string]json.RawMessage{"user": json.RawMessage(`{"uuid":"uuid-c"}`)}
	if got := extractOwnerUUID(call); got != "uuid-c" {
		t.Errorf("nested user: got %q", got)
	}

	// Absent → empty.
	call = map[string]json.RawMessage{}
	if got := extractOwnerUUID(call); got != "" {
		t.Errorf("absent owner: got %q", got)
	}
}
