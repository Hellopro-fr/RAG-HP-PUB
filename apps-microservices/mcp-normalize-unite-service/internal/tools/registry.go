package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	normalizationpb "github.com/hellopro/mcp-normalize-unite/proto/gen/graph_normalization"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

// Clients holds persistent gRPC connections to backend services.
type Clients struct {
	Normalization normalizationpb.GraphNormalizationServiceClient
	Units         unitregistrypb.UnitRegistryServiceClient
	// UnitsAdminKey is sent as "authorization: Bearer <key>" on unit-registry writes only.
	UnitsAdminKey string
	// Actor is recorded as created_by / updated_by on unit-registry writes.
	Actor string
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

	r.register("normalize_quantity", normalizeQuantityDescription, normalizeQuantityInputSchema, handleNormalizeQuantity)
	r.register("normalize_range", normalizeRangeDescription, normalizeRangeInputSchema, handleNormalizeRange)
	r.register("create_unit", createUnitDescription, createUnitInputSchema, handleCreateUnit)
	r.register("update_unit", updateUnitDescription, updateUnitInputSchema, handleUpdateUnit)
	r.register("deactivate_unit", deactivateUnitDescription, unitRefInputSchema, handleDeactivateUnit)
	r.register("get_unit", getUnitDescription, unitRefInputSchema, handleGetUnit)
	r.register("create_unit_type", createUnitTypeDescription, createUnitTypeInputSchema, handleCreateUnitType)
	r.register("update_unit_type", updateUnitTypeDescription, updateUnitTypeInputSchema, handleUpdateUnitType)
	r.register("deactivate_unit_type", deactivateUnitTypeDescription, unitTypeRefInputSchema, handleDeactivateUnitType)
	r.register("get_unit_type", getUnitTypeDescription, unitTypeRefInputSchema, handleGetUnitType)
	r.register("set_dimension_types", setDimensionTypesDescription, setDimensionTypesInputSchema, handleSetDimensionTypes)

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
