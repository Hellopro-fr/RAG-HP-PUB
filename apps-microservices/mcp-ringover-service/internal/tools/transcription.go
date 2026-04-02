package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
)

const getCallTranscriptionDescription = "Get the transcription of a call"
const getCallTranscriptionInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The UUID of the call"
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

	return rawJSONResult(data), nil
}

const getCallSummaryDescription = "Get the AI-generated summary of a call"
const getCallSummaryInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The UUID of the call"
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

	return rawJSONResult(data), nil
}

const getCallMomentsDescription = "Get key moments from a call (highlights, action items)"
const getCallMomentsInputSchema = `{
	"type": "object",
	"properties": {
		"call_uuid": {
			"type": "string",
			"description": "The UUID of the call"
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

	return rawJSONResult(data), nil
}
