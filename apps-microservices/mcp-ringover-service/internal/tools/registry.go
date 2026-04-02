package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/hellopro/mcp-ringover/internal/mcp"
	"github.com/hellopro/mcp-ringover/internal/ringover"
)

// Clients holds the Ringover API client.
type Clients struct {
	Ringover *ringover.Client
}

// ToolHandler processes a tool call and returns the result.
type ToolHandler func(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error)

type registeredTool struct {
	definition mcp.Tool
	handler    ToolHandler
}

// Registry manages all MCP tools.
type Registry struct {
	tools   []registeredTool
	byName  map[string]*registeredTool
	clients *Clients
}

// NewRegistry creates a tool registry with all Ringover tools registered.
func NewRegistry(clients *Clients) *Registry {
	r := &Registry{
		byName:  make(map[string]*registeredTool),
		clients: clients,
	}

	r.register("get_calls", getCallsDescription, getCallsInputSchema, handleGetCalls)
	r.register("get_call_details", getCallDetailsDescription, getCallDetailsInputSchema, handleGetCallDetails)
	r.register("get_call_transcription", getCallTranscriptionDescription, getCallTranscriptionInputSchema, handleGetCallTranscription)
	r.register("get_call_summary", getCallSummaryDescription, getCallSummaryInputSchema, handleGetCallSummary)
	r.register("get_call_moments", getCallMomentsDescription, getCallMomentsInputSchema, handleGetCallMoments)
	r.register("list_contacts", listContactsDescription, listContactsInputSchema, handleListContacts)
	r.register("list_users", listUsersDescription, listUsersInputSchema, handleListUsers)

	return r
}

func (r *Registry) register(name, description, inputSchema string, handler ToolHandler) {
	t := registeredTool{
		definition: mcp.Tool{
			Name:        name,
			Description: description,
			InputSchema: json.RawMessage(inputSchema),
		},
		handler: handler,
	}
	r.tools = append(r.tools, t)
	r.byName[name] = &r.tools[len(r.tools)-1]
}

// ListTools returns all registered tool definitions.
func (r *Registry) ListTools() []mcp.Tool {
	tools := make([]mcp.Tool, len(r.tools))
	for i, t := range r.tools {
		tools[i] = t.definition
	}
	return tools
}

// CallTool dispatches a tool call to the appropriate handler.
func (r *Registry) CallTool(ctx context.Context, params *mcp.CallToolParams) *mcp.CallToolResult {
	t, found := r.byName[params.Name]
	if !found {
		return errorResult(fmt.Sprintf("unknown tool: %s", params.Name))
	}

	result, err := t.handler(ctx, r.clients, params.Arguments)
	if err != nil {
		log.Printf("[tools] error in %s: %v", params.Name, err)
		return errorResult(fmt.Sprintf("tool execution failed: %v", err))
	}

	return result
}

func errorResult(msg string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		Content: []mcp.ContentBlock{{Type: "text", Text: msg}},
		IsError: true,
	}
}

func textResult(text string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		Content: []mcp.ContentBlock{{Type: "text", Text: text}},
	}
}

func jsonResult(v any) *mcp.CallToolResult {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return errorResult(fmt.Sprintf("failed to marshal result: %v", err))
	}
	return textResult(string(b))
}

func rawJSONResult(data json.RawMessage) *mcp.CallToolResult {
	return textResult(string(data))
}
