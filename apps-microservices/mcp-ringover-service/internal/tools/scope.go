package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"

	"github.com/hellopro/mcp-ringover/internal/transport"
)

// effectiveUserIDs computes the final user-id filter applied to outbound
// Ringover API calls, combining any caller-supplied user_id with the
// gateway-enforced scope (if any).
//
// Returns:
//   - ids: the list to pass to the API (nil = unrestricted, [n] = single user)
//   - err: non-nil when the caller asked for a user outside the scope (access denial),
//     or when the caller supplied a non-numeric user_id, or when the scope is
//     declared empty (deny-all).
func effectiveUserIDs(ctx context.Context, callerUserID string) ([]int, error) {
	allowed, restricted := transport.AllowedUserIDsFromContext(ctx)
	if !restricted {
		// No gateway scope — honour the caller's filter as-is.
		if callerUserID == "" {
			return nil, nil
		}
		id, err := strconv.Atoi(callerUserID)
		if err != nil {
			return nil, fmt.Errorf("user_id must be numeric: %q", callerUserID)
		}
		return []int{id}, nil
	}
	// Gateway scope active.
	if len(allowed) == 0 {
		return nil, fmt.Errorf("access denied: token scope grants access to no Ringover users")
	}
	if callerUserID == "" {
		return allowed, nil
	}
	id, err := strconv.Atoi(callerUserID)
	if err != nil {
		return nil, fmt.Errorf("user_id must be numeric: %q", callerUserID)
	}
	for _, a := range allowed {
		if a == id {
			return []int{id}, nil
		}
	}
	return nil, fmt.Errorf("user_id %d is not permitted by the current token scope", id)
}

// checkCallOwnedByAllowed verifies that the given Ringover user_id is within
// the scope declared by the gateway. Returns nil when no scope is active.
// When the scope is active and the user_id is 0 (unknown/missing from the API
// response), access is denied — fail-closed.
func checkCallOwnedByAllowed(ctx context.Context, callUserID int) error {
	allowed, restricted := transport.AllowedUserIDsFromContext(ctx)
	if !restricted {
		return nil
	}
	if callUserID == 0 {
		return fmt.Errorf("call ownership could not be determined; access denied by token scope")
	}
	for _, a := range allowed {
		if a == callUserID {
			return nil
		}
	}
	return fmt.Errorf("call owner (user_id=%d) is not permitted by the current token scope", callUserID)
}

// callItem captures the per-call fields we extract from a Ringover calls
// response. user_id appears at the top level in the list/search endpoints but
// is nested under "user" in the /calls/{id} detail response, so both are
// modelled.
type callItem struct {
	UserID int `json:"user_id"`
	User   struct {
		UserID int `json:"user_id"`
	} `json:"user"`
}

// firstCallItem returns the first call from a Ringover calls response,
// tolerating both envelopes: GET /calls/{id} returns { list: [...] } while the
// list/search endpoints return { call_list: [...] }. A bare object is accepted
// as a defensive fallback. ok is false when no call could be parsed.
func firstCallItem(body json.RawMessage) (callItem, bool) {
	var env struct {
		List     []callItem `json:"list"`
		CallList []callItem `json:"call_list"`
	}
	if err := json.Unmarshal(body, &env); err == nil {
		if len(env.List) > 0 {
			return env.List[0], true
		}
		if len(env.CallList) > 0 {
			return env.CallList[0], true
		}
	}
	var bare callItem
	if err := json.Unmarshal(body, &bare); err == nil {
		return bare, true
	}
	return callItem{}, false
}

// extractCallUserID parses the owning agent's user_id from a Ringover call
// response. Returns 0 when absent or unparseable — callers must treat 0 as
// "unknown" (the scope check fails closed on 0).
func extractCallUserID(body json.RawMessage) int {
	item, ok := firstCallItem(body)
	if !ok {
		return 0
	}
	if item.UserID != 0 {
		return item.UserID
	}
	return item.User.UserID
}

// callTypeForPostCalls normalises a single call_type string (used by the
// search_calls tool) to the slice form accepted by POST /calls.
func callTypeForPostCalls(callType string) []string {
	if callType == "" {
		return nil
	}
	return []string{callType}
}

// effectiveStatsUserID resolves the single user_id to send to /stats/team
// under the active token scope.
//
// /stats/team accepts zero or one user_id query param; it has no multi-user
// filter, so a scope wider than one user cannot be expressed server-side when
// the caller did not narrow it themselves.
//
// Returns:
//   - "" when unrestricted and no caller filter (pass-through = all users)
//   - "<id>" when exactly one user is effectively allowed
//   - err when the caller's user_id lies outside the scope, or when the scope
//     allows multiple users and the caller did not pick one
func effectiveStatsUserID(ctx context.Context, callerUserID string) (string, error) {
	ids, err := effectiveUserIDs(ctx, callerUserID)
	if err != nil {
		return "", err
	}
	if len(ids) == 0 {
		return "", nil
	}
	if len(ids) == 1 {
		return strconv.Itoa(ids[0]), nil
	}
	return "", fmt.Errorf("token scope allows multiple Ringover users (%d); specify user_id to pick one", len(ids))
}
