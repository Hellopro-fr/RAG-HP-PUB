package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	"github.com/hellopro/mcp-classification-produit/internal/mcp"
)

// Clients holds the HTTP client and base URL for the classification API.
type Clients struct {
	HTTP    *http.Client
	BaseURL string // e.g. "http://api-classification-lb:80"
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

	r.register("classify_product", classifyDescription, classifyInputSchema, handleClassifyProduct)
	r.register("classify_products_batch", classifyBatchDescription, classifyBatchInputSchema, handleClassifyProductsBatch)
	r.register("list_cached_categories", listCachedCategoriesDescription, listCachedCategoriesInputSchema, handleListCachedCategories)
	r.register("get_cached_category", getCachedCategoryDescription, getCachedCategoryInputSchema, handleGetCachedCategory)

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
