package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	llmpb "github.com/hellopro/mcp-api-recherche/proto/gen/llm"
	"google.golang.org/protobuf/encoding/protojson"
)

const llmChatDescription = "Send a prompt to the internal LLM service (vLLM-hosted models). " +
	"Use this only when you need a response from a specific model hosted in the HelloPro infrastructure, " +
	"not for general-purpose chat."

const llmChatInputSchema = `{
	"type": "object",
	"properties": {
		"message": {
			"type": "string",
			"description": "The prompt message to send to the LLM"
		},
		"temperature": {
			"type": "number",
			"description": "Sampling temperature (0.0 = deterministic, 1.0 = creative)",
			"default": 0.0
		},
		"max_tokens": {
			"type": "integer",
			"description": "Maximum tokens in the response",
			"default": 4096
		}
	},
	"required": ["message"]
}`

func handleLLMChat(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	message, ok := args["message"].(string)
	if !ok || message == "" {
		return errorResult("'message' parameter is required and must be a string"), nil
	}

	req := &llmpb.ChatRequest{
		Message: message,
	}

	if temp, ok := args["temperature"].(float64); ok {
		t := float32(temp)
		req.Temperature = &t
	}

	if maxTokens, ok := args["max_tokens"].(float64); ok {
		mt := int32(maxTokens)
		req.MaxTokens = &mt
	}

	resp, err := clients.LLM.Chat(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("LLM Chat gRPC call failed: %w", err)
	}

	// Convert protobuf Struct to JSON
	fullMsg := resp.GetFullMessage()
	if fullMsg == nil {
		return textResult("(empty response from LLM)"), nil
	}

	jsonBytes, err := protojson.Marshal(fullMsg)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal LLM response: %w", err)
	}

	var parsed any
	if err := json.Unmarshal(jsonBytes, &parsed); err != nil {
		return textResult(string(jsonBytes)), nil
	}

	return jsonResult(parsed), nil
}
