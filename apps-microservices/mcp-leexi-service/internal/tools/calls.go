package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-leexi/internal/mcp"
)

// ── search_calls ─────────────────────────────────────────────────────────────

const searchCallsDescription = "Search and list calls/meetings from Leexi. Supports date range filtering, sorting, owner filtering, and pagination."
const searchCallsInputSchema = `{
	"type": "object",
	"properties": {
		"from": {
			"type": "string",
			"description": "Start date filter (ISO 8601, e.g. 2026-04-01T00:00:00.000Z)"
		},
		"to": {
			"type": "string",
			"description": "End date filter (ISO 8601, e.g. 2026-04-03T23:59:59.000Z)"
		},
		"order": {
			"type": "string",
			"description": "Sort order for results",
			"enum": ["created_at desc", "created_at asc", "performed_at desc", "performed_at asc", "updated_at desc", "updated_at asc"],
			"default": "created_at desc"
		},
		"owner_uuid": {
			"type": "string",
			"description": "Filter by call owner UUID"
		},
		"with_simple_transcript": {
			"type": "boolean",
			"description": "Include transcript text in list results (default: false)",
			"default": false
		},
		"page": {
			"type": "integer",
			"description": "Page number for pagination (default: 1)",
			"default": 1
		},
		"items": {
			"type": "integer",
			"description": "Number of results per page (1-100, default: 10)",
			"default": 10
		}
	}
}`

func handleSearchCalls(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	from, _ := args["from"].(string)
	to, _ := args["to"].(string)
	order, _ := args["order"].(string)
	ownerUUID, _ := args["owner_uuid"].(string)
	withTranscript := false
	if v, ok := args["with_simple_transcript"].(bool); ok {
		withTranscript = v
	}
	page := 1
	if v, ok := args["page"]; ok {
		if f, ok := v.(float64); ok {
			page = int(f)
		}
	}
	items := 10
	if v, ok := args["items"]; ok {
		if f, ok := v.(float64); ok {
			items = int(f)
		}
	}

	data, err := clients.Leexi.SearchCalls(ctx, from, to, order, ownerUUID, withTranscript, page, items)
	if err != nil {
		return nil, fmt.Errorf("SearchCalls: %w", err)
	}
	return rawJSONResult(data), nil
}

// ── get_call_transcript ──────────────────────────────────────────────────────

const getCallTranscriptDescription = "Get the full transcript of a call or meeting by UUID. Returns paragraph-level and word-level timestamped transcription with speaker attribution."
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
	for _, key := range []string{"uuid", "title", "transcript", "simple_transcript", "call_topics", "speakers", "duration"} {
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

const getCallSummaryDescription = "Get the AI-generated summary of a call or meeting by UUID. Includes AI prompts/completions, chapters, and key topics."
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
	for _, key := range []string{"uuid", "title", "prompts", "chapters", "call_topics", "duration", "performed_at", "speakers"} {
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
