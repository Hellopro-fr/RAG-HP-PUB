package tools

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/hellopro/mcp-ringover/internal/transport"
)

func TestFilterUserListResponse_Unrestricted(t *testing.T) {
	raw := json.RawMessage(`{"user_list":[{"user_id":1},{"user_id":2},{"user_id":3}]}`)
	out, err := filterUserListResponse(context.Background(), raw)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	// Unrestricted should pass through unchanged.
	if string(out) != string(raw) {
		t.Errorf("expected passthrough, got %s", string(out))
	}
}

func TestFilterUserListResponse_Restricted(t *testing.T) {
	raw := json.RawMessage(`{"user_list":[{"user_id":1},{"user_id":2},{"user_id":3}],"user_list_count":3}`)
	ctx := transport.WithAllowedUserIDsForTest(context.Background(), []int{2}, true)

	out, err := filterUserListResponse(ctx, raw)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	s := string(out)
	// Only user_id=2 should remain, ids 1 and 3 filtered out.
	if !strings.Contains(s, `"user_id":2`) {
		t.Errorf("expected user_id=2 to be kept, got %s", s)
	}
	if strings.Contains(s, `"user_id":1`) || strings.Contains(s, `"user_id":3`) {
		t.Errorf("expected ids 1 and 3 to be filtered, got %s", s)
	}
}

func TestFilterUserListResponse_DenyAll(t *testing.T) {
	raw := json.RawMessage(`{"user_list":[{"user_id":1}]}`)
	ctx := transport.WithAllowedUserIDsForTest(context.Background(), nil, true)

	out, err := filterUserListResponse(ctx, raw)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !strings.Contains(string(out), `"user_list":[]`) {
		t.Errorf("deny-all should yield empty user_list, got %s", string(out))
	}
}
