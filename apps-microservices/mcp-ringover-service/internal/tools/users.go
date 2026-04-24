package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
	"github.com/hellopro/mcp-ringover/internal/transport"
)

const listUsersDescription = "List all Ringover users"
const listUsersInputSchema = `{
	"type": "object",
	"properties": {}
}`

func handleListUsers(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	data, err := clients.Ringover.GetUsers(ctx)
	if err != nil {
		return nil, fmt.Errorf("GetUsers: %w", err)
	}

	scoped, err := filterUserListResponse(ctx, data)
	if err != nil {
		return nil, fmt.Errorf("filter users: %w", err)
	}
	return rawJSONResult(scoped), nil
}

// filterUserListResponse drops every user whose user_id is not in the
// gateway-issued allowed set. Returns the payload unchanged when no scope is
// active. The user_list_count field is updated when present.
func filterUserListResponse(ctx context.Context, raw json.RawMessage) (json.RawMessage, error) {
	allowed, restricted := transport.AllowedUserIDsFromContext(ctx)
	if !restricted {
		return raw, nil
	}
	allowedSet := make(map[int]struct{}, len(allowed))
	for _, id := range allowed {
		allowedSet[id] = struct{}{}
	}

	// Decode into a map so we can preserve all unrelated fields verbatim while
	// replacing only user_list and user_list_count.
	var envelope map[string]json.RawMessage
	if err := json.Unmarshal(raw, &envelope); err != nil {
		// Fallback: bare array.
		var arr []json.RawMessage
		if err2 := json.Unmarshal(raw, &arr); err2 != nil {
			return nil, fmt.Errorf("unrecognised users response shape: %w", err)
		}
		filtered := filterUserArray(arr, allowedSet)
		return json.Marshal(filtered)
	}

	// Ringover's real /users response uses `list` + `list_count`, but we
	// tolerate the older `user_list` + `user_list_count` envelope too so
	// non-gateway callers that rely on either shape keep working.
	listKey := ""
	countKey := ""
	if _, ok := envelope["list"]; ok {
		listKey, countKey = "list", "list_count"
	} else if _, ok := envelope["user_list"]; ok {
		listKey, countKey = "user_list", "user_list_count"
	}

	if listKey == "" {
		// Nothing to filter — safer to return an empty list than to leak
		// unfiltered data under a declared scope.
		envelope["list"] = json.RawMessage(`[]`)
		envelope["list_count"] = json.RawMessage(`0`)
		return json.Marshal(envelope)
	}

	var arr []json.RawMessage
	if err := json.Unmarshal(envelope[listKey], &arr); err != nil {
		return nil, fmt.Errorf("%s is not an array: %w", listKey, err)
	}
	filtered := filterUserArray(arr, allowedSet)
	encoded, err := json.Marshal(filtered)
	if err != nil {
		return nil, err
	}
	envelope[listKey] = encoded
	if _, hasCount := envelope[countKey]; hasCount {
		envelope[countKey] = json.RawMessage(fmt.Sprintf("%d", len(filtered)))
	}
	return json.Marshal(envelope)
}

func filterUserArray(arr []json.RawMessage, allowedSet map[int]struct{}) []json.RawMessage {
	out := make([]json.RawMessage, 0, len(arr))
	for _, entry := range arr {
		var probe struct {
			UserID int `json:"user_id"`
		}
		if err := json.Unmarshal(entry, &probe); err != nil {
			continue
		}
		if _, ok := allowedSet[probe.UserID]; ok {
			out = append(out, entry)
		}
	}
	return out
}
