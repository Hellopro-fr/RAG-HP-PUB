package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
	"github.com/hellopro/mcp-ringover/internal/ringover"
	"github.com/hellopro/mcp-ringover/internal/transport"
)

const getCallsDescription = "List recent calls from Ringover with optional limit"
const getCallsInputSchema = `{
	"type": "object",
	"properties": {
		"limit": {
			"type": "integer",
			"description": "Maximum number of calls to return (default: 20)",
			"default": 20
		}
	}
}`

func handleGetCalls(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	limit := 20
	if v, ok := args["limit"]; ok {
		if f, ok := v.(float64); ok {
			limit = int(f)
		}
	}

	if allowed, restricted := transport.AllowedUserIDsFromContext(ctx); restricted {
		if len(allowed) == 0 {
			return errorResult("access denied: token scope grants access to no Ringover users"), nil
		}
		data, err := clients.Ringover.PostCalls(ctx, ringover.PostCallsRequest{
			Filter:     "ADVANCED",
			LimitCount: limit,
			Advanced:   &ringover.AdvancedCallsFilter{Users: allowed},
		})
		if err != nil {
			return nil, fmt.Errorf("PostCalls: %w", err)
		}
		return rawJSONResult(data), nil
	}

	data, err := clients.Ringover.GetCalls(ctx, limit)
	if err != nil {
		return nil, fmt.Errorf("GetCalls: %w", err)
	}

	return rawJSONResult(data), nil
}

// ── list_calls_by_date ───────────────────────────────────────────────────────

const listCallsByDateDescription = "List calls within a date range. Dates must be ISO 8601 (e.g. 2026-04-01T00:00:00.000Z) or YYYY-MM-DD."
const listCallsByDateInputSchema = `{
	"type": "object",
	"properties": {
		"start_date": {
			"type": "string",
			"description": "Start of the date range (ISO 8601 or YYYY-MM-DD)"
		},
		"end_date": {
			"type": "string",
			"description": "End of the date range (ISO 8601 or YYYY-MM-DD)"
		},
		"limit": {
			"type": "integer",
			"description": "Maximum number of calls to return (default: 50)",
			"default": 50
		}
	},
	"required": ["start_date", "end_date"]
}`

func handleListCallsByDate(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	startDate, ok := args["start_date"].(string)
	if !ok || startDate == "" {
		return errorResult("'start_date' parameter is required"), nil
	}
	endDate, ok := args["end_date"].(string)
	if !ok || endDate == "" {
		return errorResult("'end_date' parameter is required"), nil
	}
	limit := 50
	if v, ok := args["limit"]; ok {
		if f, ok := v.(float64); ok {
			limit = int(f)
		}
	}

	// When the gateway has declared a user scope, use POST /calls with
	// advanced.users for server-side filtering. GET /calls has no user filter.
	if allowed, restricted := transport.AllowedUserIDsFromContext(ctx); restricted {
		if len(allowed) == 0 {
			return errorResult("access denied: token scope grants access to no Ringover users"), nil
		}
		data, err := clients.Ringover.PostCalls(ctx, ringover.PostCallsRequest{
			Filter:     "ADVANCED",
			StartDate:  startDate,
			EndDate:    endDate,
			LimitCount: limit,
			Advanced:   &ringover.AdvancedCallsFilter{Users: allowed},
		})
		if err != nil {
			return nil, fmt.Errorf("PostCalls: %w", err)
		}
		return rawJSONResult(data), nil
	}

	data, err := clients.Ringover.ListCallsByDate(ctx, startDate, endDate, limit)
	if err != nil {
		return nil, fmt.Errorf("ListCallsByDate: %w", err)
	}
	return rawJSONResult(data), nil
}

// ── search_calls ─────────────────────────────────────────────────────────────

const searchCallsDescription = "Search and filter calls by type, phone number, or user. All parameters are optional. Use call_type to filter by ANSWERED, MISSED, OUT (outbound), or VOICEMAIL."
const searchCallsInputSchema = `{
	"type": "object",
	"properties": {
		"call_type": {
			"type": "string",
			"description": "Filter by call type: ANSWERED (answered inbound/outbound), MISSED (missed inbound), OUT (outbound), VOICEMAIL",
			"enum": ["ANSWERED", "MISSED", "OUT", "VOICEMAIL"]
		},
		"phone_number": {
			"type": "string",
			"description": "Filter by phone number (caller or callee)"
		},
		"user_id": {
			"type": "string",
			"description": "Filter by Ringover user ID"
		},
		"limit": {
			"type": "integer",
			"description": "Maximum number of results (default: 20)",
			"default": 20
		}
	}
}`

func handleSearchCalls(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callType, _ := args["call_type"].(string)
	phoneNumber, _ := args["phone_number"].(string)
	userID, _ := args["user_id"].(string)
	limit := 20
	if v, ok := args["limit"]; ok {
		if f, ok := v.(float64); ok {
			limit = int(f)
		}
	}

	// Resolve the effective user-id filter: intersect caller filter with scope.
	effectiveIDs, err := effectiveUserIDs(ctx, userID)
	if err != nil {
		return errorResult(err.Error()), nil
	}

	// Path 1: caller or scope narrows the filter to specific users → POST /calls.
	// phone_number cannot be combined with POST /calls.advanced.users in the
	// same request (the advanced sub-object only supports users/groups/etc.),
	// so we prefer the user-scope filter and drop phone_number when both are
	// specified. If no user scope, we keep the legacy GET path which accepts
	// phone_number natively.
	if len(effectiveIDs) > 0 {
		data, err := clients.Ringover.PostCalls(ctx, ringover.PostCallsRequest{
			Filter:     "ADVANCED",
			CallType:   callTypeForPostCalls(callType),
			LimitCount: limit,
			Advanced:   &ringover.AdvancedCallsFilter{Users: effectiveIDs},
		})
		if err != nil {
			return nil, fmt.Errorf("PostCalls: %w", err)
		}
		return rawJSONResult(data), nil
	}

	// Path 2: unrestricted and no caller user_id → preserve the existing GET behaviour.
	data, err := clients.Ringover.SearchCalls(ctx, callType, phoneNumber, "", limit)
	if err != nil {
		return nil, fmt.Errorf("SearchCalls: %w", err)
	}
	return rawJSONResult(data), nil
}

// ── get_call_stats_by_user ───────────────────────────────────────────────────

const getCallStatsByUserDescription = "Get call statistics broken down by user/team member for a date range."
const getCallStatsByUserInputSchema = `{
	"type": "object",
	"properties": {
		"start_date": {
			"type": "string",
			"description": "Start of the period (ISO 8601 or YYYY-MM-DD)"
		},
		"end_date": {
			"type": "string",
			"description": "End of the period (ISO 8601 or YYYY-MM-DD)"
		},
		"user_id": {
			"type": "string",
			"description": "Restrict to a specific user ID (optional — omit to get all users)"
		}
	},
	"required": ["start_date", "end_date"]
}`

func handleGetCallStatsByUser(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	startDate, ok := args["start_date"].(string)
	if !ok || startDate == "" {
		return errorResult("'start_date' parameter is required"), nil
	}
	endDate, ok := args["end_date"].(string)
	if !ok || endDate == "" {
		return errorResult("'end_date' parameter is required"), nil
	}
	userID, _ := args["user_id"].(string)

	data, err := clients.Ringover.GetCallStatsByUser(ctx, startDate, endDate, userID)
	if err != nil {
		return nil, fmt.Errorf("GetCallStatsByUser: %w", err)
	}
	return rawJSONResult(data), nil
}

// ── get_call_details ─────────────────────────────────────────────────────────

const getCallDetailsDescription = "Get detailed information about a specific call"
const getCallDetailsInputSchema = `{
	"type": "object",
	"properties": {
		"call_id": {
			"type": "string",
			"description": "The unique identifier of the call"
		}
	},
	"required": ["call_id"]
}`

func handleGetCallDetails(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callID, ok := args["call_id"].(string)
	if !ok || callID == "" {
		return errorResult("'call_id' parameter is required and must be a string"), nil
	}

	data, err := clients.Ringover.GetCallDetails(ctx, callID)
	if err != nil {
		return nil, fmt.Errorf("GetCallDetails: %w", err)
	}

	// Under a gateway-enforced scope, verify that the call belongs to an
	// allowed user before returning it. /calls/{id} has no filter parameter,
	// so ownership is checked post-fetch.
	if err := checkCallOwnedByAllowed(ctx, extractCallUserID(data)); err != nil {
		return errorResult(err.Error()), nil
	}

	return rawJSONResult(data), nil
}
