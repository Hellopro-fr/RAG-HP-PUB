package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
)

// extractEmpowerCallUserID reads the user_id (owning agent) from an Empower
// call-detail response. The Empower endpoints expose user_id at the top level
// alongside call_uuid, transcription, summary, etc. Returns 0 when missing.
func extractEmpowerCallUserID(body json.RawMessage) int {
	var bare struct {
		UserID int `json:"user_id"`
	}
	if err := json.Unmarshal(body, &bare); err == nil {
		return bare.UserID
	}
	return 0
}

// getEmpowerCallUUID ─────────────────────────────────────────────────────────

const getEmpowerCallUUIDDescription = "Convert a Ringover channel_id (from get_calls) to an Empower calluuid required by transcription/summary/moments tools. Requires Empower to be enabled on the API key."
const getEmpowerCallUUIDInputSchema = `{
	"type": "object",
	"properties": {
		"platform_name": {
			"type": "string",
			"description": "Empower platform name (find it in Ringover dashboard > Empower settings)"
		},
		"channel_id": {
			"type": "string",
			"description": "The channel_id from a call returned by get_calls"
		}
	},
	"required": ["platform_name", "channel_id"]
}`

func handleGetEmpowerCallUUID(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	platformName, ok := args["platform_name"].(string)
	if !ok || platformName == "" {
		return errorResult("'platform_name' parameter is required"), nil
	}
	channelID, ok := args["channel_id"].(string)
	if !ok || channelID == "" {
		return errorResult("'channel_id' parameter is required"), nil
	}

	data, err := clients.Ringover.GetEmpowerCallUUID(ctx, platformName, channelID)
	if err != nil {
		return nil, fmt.Errorf("GetEmpowerCallUUID: %w", err)
	}

	return rawJSONResult(data), nil
}

// getCallTranscription ───────────────────────────────────────────────────────

const getCallTranscriptionDescription = "Get the full transcription of a call (requires Empower). Use get_empower_call_uuid first to convert a channel_id from get_calls into the calluuid needed here."
const getCallTranscriptionInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The Empower calluuid (obtained via get_empower_call_uuid, NOT the Ringover call_id)"
		}
	},
	"required": ["call_uuid"]
}`

func handleGetCallTranscription(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callUUID, ok := args["call_uuid"].(string)
	if !ok || callUUID == "" {
		return errorResult("'call_uuid' parameter is required and must be a string"), nil
	}

	data, err := clients.Ringover.GetCallTranscription(ctx, callUUID)
	if err != nil {
		return nil, fmt.Errorf("GetCallTranscription: %w", err)
	}

	if err := checkCallOwnedByAllowed(ctx, extractEmpowerCallUserID(data)); err != nil {
		return errorResult(err.Error()), nil
	}

	return rawJSONResult(data), nil
}

const getCallSummaryDescription = "Get the AI-generated summary of a call (requires Empower). Use get_empower_call_uuid first to convert a channel_id from get_calls into the calluuid needed here."
const getCallSummaryInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The Empower calluuid (obtained via get_empower_call_uuid, NOT the Ringover call_id)"
		}
	},
	"required": ["call_uuid"]
}`

func handleGetCallSummary(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callUUID, ok := args["call_uuid"].(string)
	if !ok || callUUID == "" {
		return errorResult("'call_uuid' parameter is required and must be a string"), nil
	}

	data, err := clients.Ringover.GetCallSummary(ctx, callUUID)
	if err != nil {
		return nil, fmt.Errorf("GetCallSummary: %w", err)
	}

	if err := checkCallOwnedByAllowed(ctx, extractEmpowerCallUserID(data)); err != nil {
		return errorResult(err.Error()), nil
	}

	return rawJSONResult(data), nil
}

const getCallMomentsDescription = "Get key moments from a call: highlights, action items, topics (requires Empower). Use get_empower_call_uuid first to convert a channel_id from get_calls into the calluuid needed here."
const getCallMomentsInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The Empower calluuid (obtained via get_empower_call_uuid, NOT the Ringover call_id)"
		}
	},
	"required": ["call_uuid"]
}`

func handleGetCallMoments(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	callUUID, ok := args["call_uuid"].(string)
	if !ok || callUUID == "" {
		return errorResult("'call_uuid' parameter is required and must be a string"), nil
	}

	data, err := clients.Ringover.GetCallMoments(ctx, callUUID)
	if err != nil {
		return nil, fmt.Errorf("GetCallMoments: %w", err)
	}

	if err := checkCallOwnedByAllowed(ctx, extractEmpowerCallUserID(data)); err != nil {
		return errorResult(err.Error()), nil
	}

	return rawJSONResult(data), nil
}
