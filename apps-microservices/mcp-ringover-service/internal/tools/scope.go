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

// extractCallUserID parses the user_id of a call from Ringover's response.
// The /calls/{id} endpoint returns { call_list: [ { user_id, ... } ] }; some
// proxies return a bare object. Returns 0 when the field is absent or cannot
// be parsed — callers must treat 0 as "unknown".
func extractCallUserID(body json.RawMessage) int {
	// Envelope: { call_list: [...] }
	var envelope struct {
		CallList []struct {
			UserID int `json:"user_id"`
		} `json:"call_list"`
	}
	if err := json.Unmarshal(body, &envelope); err == nil && len(envelope.CallList) > 0 {
		return envelope.CallList[0].UserID
	}
	// Bare object fallback.
	var bare struct {
		UserID int `json:"user_id"`
	}
	if err := json.Unmarshal(body, &bare); err == nil {
		return bare.UserID
	}
	return 0
}

// callTypeForPostCalls normalises a single call_type string (used by the
// search_calls tool) to the slice form accepted by POST /calls.
func callTypeForPostCalls(callType string) []string {
	if callType == "" {
		return nil
	}
	return []string{callType}
}
