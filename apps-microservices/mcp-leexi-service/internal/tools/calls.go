package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-leexi/internal/mcp"
)

// ── search_calls ─────────────────────────────────────────────────────────────

const searchCallsDescription = "Search and list calls/meetings from Leexi. Supports optional date range filtering and pagination."
const searchCallsInputSchema = `{
	"type": "object",
	"properties": {
		"start_date": {
			"type": "string",
			"description": "Filter calls starting from this date (ISO 8601, e.g. 2026-04-01)"
		},
		"end_date": {
			"type": "string",
			"description": "Filter calls up to this date (ISO 8601, e.g. 2026-04-03)"
		},
		"page": {
			"type": "integer",
			"description": "Page number for pagination (default: 1)",
			"default": 1
		},
		"per_page": {
			"type": "integer",
			"description": "Number of results per page (default: 25)",
			"default": 25
		}
	}
}`

func handleSearchCalls(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	startDate, _ := args["start_date"].(string)
	endDate, _ := args["end_date"].(string)
	page := 1
	if v, ok := args["page"]; ok {
		if f, ok := v.(float64); ok {
			page = int(f)
		}
	}
	perPage := 25
	if v, ok := args["per_page"]; ok {
		if f, ok := v.(float64); ok {
			perPage = int(f)
		}
	}

	data, err := clients.Leexi.SearchCalls(ctx, startDate, endDate, page, perPage)
	if err != nil {
		return nil, fmt.Errorf("SearchCalls: %w", err)
	}
	return rawJSONResult(data), nil
}

// ── get_call_transcript ──────────────────────────────────────────────────────

const getCallTranscriptDescription = "Get the full transcript of a call or meeting by UUID. Returns paragraph-level and word-level timestamped transcription."
const getCallTranscriptInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The unique identifier (UUID) of the call or meeting"
		}
	},
	"required": ["call_uuid"]
}`

func handleGetCallTranscript(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callUUID, ok := args["call_uuid"].(string)
	if !ok || callUUID == "" {
		return errorResult("'call_uuid' parameter is required"), nil
	}

	data, err := clients.Leexi.GetCall(ctx, callUUID)
	if err != nil {
		return nil, fmt.Errorf("GetCall: %w", err)
	}

	// Extract transcript-related fields from the full call response.
	var full map[string]json.RawMessage
	if err := json.Unmarshal(data, &full); err != nil {
		return rawJSONResult(data), nil
	}

	transcript := map[string]json.RawMessage{}
	for _, key := range []string{"uuid", "title", "transcript", "simple_transcript", "topics"} {
		if v, exists := full[key]; exists {
			transcript[key] = v
		}
	}

	result, err := json.MarshalIndent(transcript, "", "  ")
	if err != nil {
		return rawJSONResult(data), nil
	}
	return textResult(string(result)), nil
}

// ── get_call_summary ─────────────────────────────────────────────────────────

const getCallSummaryDescription = "Get the AI-generated summary of a call or meeting by UUID. Includes summary, chaptering, and key topics."
const getCallSummaryInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The unique identifier (UUID) of the call or meeting"
		}
	},
	"required": ["call_uuid"]
}`

func handleGetCallSummary(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callUUID, ok := args["call_uuid"].(string)
	if !ok || callUUID == "" {
		return errorResult("'call_uuid' parameter is required"), nil
	}

	data, err := clients.Leexi.GetCall(ctx, callUUID)
	if err != nil {
		return nil, fmt.Errorf("GetCall: %w", err)
	}

	// Extract summary-related fields from the full call response.
	var full map[string]json.RawMessage
	if err := json.Unmarshal(data, &full); err != nil {
		return rawJSONResult(data), nil
	}

	summary := map[string]json.RawMessage{}
	for _, key := range []string{"uuid", "title", "summary", "chaptering", "topics", "duration", "started_at"} {
		if v, exists := full[key]; exists {
			summary[key] = v
		}
	}

	result, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return rawJSONResult(data), nil
	}
	return textResult(string(result)), nil
}
