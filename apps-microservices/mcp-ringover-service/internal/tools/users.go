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

	listRaw, ok := envelope["user_list"]
	if !ok {
		// Nothing to filter — safer to return empty than to leak unfiltered data.
		envelope["user_list"] = json.RawMessage(`[]`)
		if _, hasCount := envelope["user_list_count"]; hasCount {
			envelope["user_list_count"] = json.RawMessage(`0`)
		}
		return json.Marshal(envelope)
	}

	var arr []json.RawMessage
	if err := json.Unmarshal(listRaw, &arr); err != nil {
		return nil, fmt.Errorf("user_list is not an array: %w", err)
	}
	filtered := filterUserArray(arr, allowedSet)
	encoded, err := json.Marshal(filtered)
	if err != nil {
		return nil, err
	}
	envelope["user_list"] = encoded
	if _, hasCount := envelope["user_list_count"]; hasCount {
		envelope["user_list_count"] = json.RawMessage(fmt.Sprintf("%d", len(filtered)))
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
