package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
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

	data, err := clients.Ringover.GetCalls(ctx, limit)
	if err != nil {
		return nil, fmt.Errorf("GetCalls: %w", err)
	}

	return rawJSONResult(data), nil
}

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

	return rawJSONResult(data), nil
}
