package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
	embeddingpb "github.com/hellopro/mcp-api-recherche/proto/gen/embedding"
	llmpb "github.com/hellopro/mcp-api-recherche/proto/gen/llm"
	rerankingpb "github.com/hellopro/mcp-api-recherche/proto/gen/reranking"
)

// Clients holds persistent gRPC connections to backend services.
type Clients struct {
	Embedding embeddingpb.EmbeddingServiceClient
	Database  databasepb.DatabaseSearchServiceClient
	Reranking rerankingpb.RerankingServiceClient
	LLM       llmpb.LLMServiceClient
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

// NewRegistry creates a tool registry with all tools registered.
func NewRegistry(clients *Clients) *Registry {
	r := &Registry{
		byName:  make(map[string]*registeredTool),
		clients: clients,
	}

	r.register("search", searchDescription, searchInputSchema, handleSearch)
	r.register("classic_search", classicSearchDescription, classicSearchInputSchema, handleClassicSearch)
	r.register("get_collection_schema", schemaDescription, schemaInputSchema, handleGetCollectionSchema)
	r.register("rerank", rerankDescription, rerankInputSchema, handleRerank)
	r.register("embed_text", embedDescription, embedInputSchema, handleEmbedText)
	r.register("llm_chat", llmChatDescription, llmChatInputSchema, handleLLMChat)

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
