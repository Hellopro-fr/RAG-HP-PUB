package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-leexi/internal/mcp"
	"github.com/hellopro/mcp-leexi/internal/transport"
)

// effectiveParticipantUUIDs computes the final participating_user_uuid[] list
// sent to the Leexi API, combining any user-supplied filter with the
// gateway-enforced scope.
//
// Returns:
//   - participants: the intersection to pass to the API (may be empty = unrestricted)
//   - err:          non-nil when the caller requested a participant UUID outside
//                   the scope allowed by the token (access denial).
func effectiveParticipantUUIDs(ctx context.Context, requested string) ([]string, error) {
	allowed, restricted := transport.AllowedParticipantsFromContext(ctx)
	if !restricted {
		// No scope enforcement — honour the user-supplied filter as before.
		if requested == "" {
			return nil, nil
		}
		return []string{requested}, nil
	}
	if requested == "" {
		// User did not specify — force the full allowed list.
		return allowed, nil
	}
	// User did specify — only accept if it intersects the allowed set.
	for _, a := range allowed {
		if a == requested {
			return []string{requested}, nil
		}
	}
	return nil, fmt.Errorf("participating_user_uuid %q is not permitted by the current token scope", requested)
}

// isParticipantAllowed reports whether a single UUID is within the scope
// declared by the gateway (or true when no scope is declared).
func isParticipantAllowed(ctx context.Context, uuid string) bool {
	allowed, restricted := transport.AllowedParticipantsFromContext(ctx)
	if !restricted {
		return true
	}
	for _, a := range allowed {
		if a == uuid {
			return true
		}
	}
	return false
}

// checkCallParticipantAllowed verifies that at least one of the allowed
// participant UUIDs appears in the call's participants/speakers list. Falls
// back to checking owner_uuid when participant data is unavailable.
// Denies access when the gateway declared a restricted scope and no match is found.
func checkCallParticipantAllowed(ctx context.Context, call map[string]json.RawMessage) error {
	allowed, restricted := transport.AllowedParticipantsFromContext(ctx)
	if !restricted {
		return nil
	}

	allowedSet := make(map[string]struct{}, len(allowed))
	for _, a := range allowed {
		allowedSet[a] = struct{}{}
	}

	// Try speakers[].uuid first (most reliable participant data).
	if uuids := extractSpeakerUUIDs(call); len(uuids) > 0 {
		for _, u := range uuids {
			if _, ok := allowedSet[u]; ok {
				return nil
			}
		}
		return fmt.Errorf("none of the call participants are permitted by the current token scope")
	}

	// Fallback: check owner_uuid (the owner is always a participant).
	ownerUUID := extractOwnerUUID(call)
	if ownerUUID != "" {
		if _, ok := allowedSet[ownerUUID]; ok {
			return nil
		}
		return fmt.Errorf("call participant/owner %q is not permitted by the current token scope", ownerUUID)
	}

	// Neither speakers nor owner could be determined — fail closed.
	return fmt.Errorf("call participants could not be determined; access denied by token scope")
}

// extractSpeakerUUIDs returns the UUIDs from the call's "speakers" array.
// Tolerates both {uuid: "..."} objects and plain string entries.
func extractSpeakerUUIDs(call map[string]json.RawMessage) []string {
	raw, ok := call["speakers"]
	if !ok || len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	// Try array of objects with uuid field.
	var speakers []struct {
		UUID string `json:"uuid"`
	}
	if json.Unmarshal(raw, &speakers) == nil {
		uuids := make([]string, 0, len(speakers))
		for _, s := range speakers {
			if s.UUID != "" {
				uuids = append(uuids, s.UUID)
			}
		}
		if len(uuids) > 0 {
			return uuids
		}
	}
	return nil
}

// extractOwnerUUID tolerates the common shapes Leexi uses to expose the
// owning user on a call payload: top-level "owner_uuid", nested
// {"owner":{"uuid":…}}, or nested {"user":{"uuid":…}}.
func extractOwnerUUID(call map[string]json.RawMessage) string {
	if raw, ok := call["owner_uuid"]; ok {
		var s string
		if json.Unmarshal(raw, &s) == nil && s != "" {
			return s
		}
	}
	for _, key := range []string{"owner", "user"} {
		if raw, ok := call[key]; ok && len(raw) > 0 && string(raw) != "null" {
			var nested struct {
				UUID string `json:"uuid"`
			}
			if json.Unmarshal(raw, &nested) == nil && nested.UUID != "" {
				return nested.UUID
			}
		}
	}
	return ""
}

// ── search_calls ─────────────────────────────────────────────────────────────

const searchCallsDescription = "Search and list calls/meetings from Leexi. Supports date range filtering, sorting, participant filtering, and pagination."
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
		"participating_user_uuid": {
			"type": "string",
			"description": "Filter by participating user UUID"
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
	participantUUID, _ := args["participating_user_uuid"].(string)
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

	participantUUIDs, err := effectiveParticipantUUIDs(ctx, participantUUID)
	if err != nil {
		return errorResult(err.Error()), nil
	}

	data, err := clients.Leexi.SearchCalls(ctx, from, to, order, participantUUIDs, withTranscript, page, items)
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

	// Unwrap the "data" envelope if present.
	if inner, exists := full["data"]; exists {
		if err := json.Unmarshal(inner, &full); err == nil {
			// full now contains the actual call fields
		}
	}

	// Enforce participant-based scope: if the request context declares a
	// restricted set, reject calls whose participants are outside it.
	if err := checkCallParticipantAllowed(ctx, full); err != nil {
		return errorResult(err.Error()), nil
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

	// Unwrap the "data" envelope if present.
	if inner, exists := full["data"]; exists {
		if err := json.Unmarshal(inner, &full); err == nil {
			// full now contains the actual call fields
		}
	}

	// Enforce participant-based scope before returning anything.
	if err := checkCallParticipantAllowed(ctx, full); err != nil {
		return errorResult(err.Error()), nil
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
