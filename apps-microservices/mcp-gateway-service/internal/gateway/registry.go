package gateway

import (
	"sync"

	"github.com/hellopro/mcp-gateway/internal/mcp"
)

// BackendServer represents a registered MCP backend server.
type BackendServer struct {
	ID            string // stable UUID from the database
	URL           string // original base URL
	MessageURL    string // discovered message endpoint
	TransportType string // "sse" or "streamable-http"
	Name          string
	Version       string
	ToolPrefix    string // optional alphanumeric prefix for tool names: {prefix}_{tool_name}
	Capabilities  mcp.ServerCapabilities
	Tools         []mcp.Tool
	Resources     []mcp.Resource
	Prompts       []mcp.Prompt
	AuthHeaders   map[string]string // extra headers forwarded to this backend
}

// PrefixedToolName returns the tool name with the server prefix applied.
// If prefix is empty, returns the original name.
func PrefixedToolName(prefix, name string) string {
	if prefix == "" {
		return name
	}
	return prefix + "_" + name
}

// UnprefixedToolName strips the server prefix from a tool name.
// If the name doesn't start with the prefix, returns the original name.
func UnprefixedToolName(prefix, name string) string {
	if prefix == "" {
		return name
	}
	p := prefix + "_"
	if len(name) > len(p) && name[:len(p)] == p {
		return name[len(p):]
	}
	return name
}

// prefixedActiveTools returns a copy of active tools with the prefix applied to their names.
func prefixedActiveTools(prefix string, tools []mcp.Tool) []mcp.Tool {
	var out []mcp.Tool
	for _, t := range tools {
		if !t.IsActive {
			continue
		}
		out = append(out, mcp.Tool{
			Name:        PrefixedToolName(prefix, t.Name),
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    true,
		})
	}
	return out
}

// Registry manages the set of active backend MCP servers.
type Registry struct {
	mu      sync.RWMutex
	servers map[string]*BackendServer // keyed by ID (UUID)
}

func NewRegistry() *Registry {
	return &Registry{servers: make(map[string]*BackendServer)}
}

// Register adds or replaces a backend server entry, keyed by ID.
func (r *Registry) Register(srv *BackendServer) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.servers[srv.ID] = srv
}

// SetToolPrefix updates the tool prefix for a registered backend server.
func (r *Registry) SetToolPrefix(id, prefix string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if s, ok := r.servers[id]; ok {
		s.ToolPrefix = prefix
	}
}

// SyncToolActiveStates updates the IsActive flag for all tools of a server
// based on the provided map of tool_name → is_active.
func (r *Registry) SyncToolActiveStates(serverID string, activeStates map[string]bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if s, ok := r.servers[serverID]; ok {
		for i := range s.Tools {
			if active, exists := activeStates[s.Tools[i].Name]; exists {
				s.Tools[i].IsActive = active
			}
		}
	}
}

// SetToolActive sets the IsActive flag for a specific tool on a registered server.
func (r *Registry) SetToolActive(serverID, toolName string, active bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if s, ok := r.servers[serverID]; ok {
		for i := range s.Tools {
			if s.Tools[i].Name == toolName {
				s.Tools[i].IsActive = active
				return
			}
		}
	}
}

// Unregister removes a backend server by ID.
func (r *Registry) Unregister(id string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.servers, id)
}

// FindByID returns a backend server by its ID, or nil.
func (r *Registry) FindByID(id string) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.servers[id]
}

// All returns a snapshot of all registered servers.
func (r *Registry) All() []*BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]*BackendServer, 0, len(r.servers))
	for _, s := range r.servers {
		out = append(out, s)
	}
	return out
}

// FindByTool returns the backend that owns the named tool (with prefix matching), or nil.
// It also returns the original (unprefixed) tool name for forwarding to the backend.
// Only active tools are matched.
func (r *Registry) FindByTool(name string) (*BackendServer, string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		for _, t := range s.Tools {
			if t.IsActive && PrefixedToolName(s.ToolPrefix, t.Name) == name {
				return s, t.Name
			}
		}
	}
	return nil, ""
}

// FindByResource returns the backend that owns the given resource URI, or nil.
func (r *Registry) FindByResource(uri string) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		for _, res := range s.Resources {
			if res.URI == uri {
				return s
			}
		}
	}
	return nil
}

// FindByPrompt returns the backend that owns the named prompt, or nil.
func (r *Registry) FindByPrompt(name string) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		for _, p := range s.Prompts {
			if p.Name == name {
				return s
			}
		}
	}
	return nil
}

// MergedCapabilities returns the union of all backend capabilities.
func (r *Registry) MergedCapabilities() mcp.ServerCapabilities {
	r.mu.RLock()
	defer r.mu.RUnlock()
	caps := make([]mcp.ServerCapabilities, 0, len(r.servers))
	for _, s := range r.servers {
		caps = append(caps, s.Capabilities)
	}
	return mcp.AggregateCapabilities(caps)
}

// MergedTools returns the combined tool list from all backends, with prefixes applied.
// Only active tools are included.
func (r *Registry) MergedTools() []mcp.Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var tools []mcp.Tool
	for _, s := range r.servers {
		tools = append(tools, prefixedActiveTools(s.ToolPrefix, s.Tools)...)
	}
	return tools
}

// MergedResources returns the combined resource list from all backends.
func (r *Registry) MergedResources() []mcp.Resource {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var resources []mcp.Resource
	for _, s := range r.servers {
		resources = append(resources, s.Resources...)
	}
	return resources
}

// MergedPrompts returns the combined prompt list from all backends.
func (r *Registry) MergedPrompts() []mcp.Prompt {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var prompts []mcp.Prompt
	for _, s := range r.servers {
		prompts = append(prompts, s.Prompts...)
	}
	return prompts
}

// ── Filtered variants (for scope tokens) ─────────────────────────────────────

// MergedCapabilitiesFiltered returns merged capabilities from allowed servers only.
func (r *Registry) MergedCapabilitiesFiltered(allowed map[string]bool) mcp.ServerCapabilities {
	r.mu.RLock()
	defer r.mu.RUnlock()
	caps := make([]mcp.ServerCapabilities, 0)
	for _, s := range r.servers {
		if allowed[s.ID] {
			caps = append(caps, s.Capabilities)
		}
	}
	return mcp.AggregateCapabilities(caps)
}

// MergedToolsFiltered returns active tools from allowed servers only, with prefixes applied.
func (r *Registry) MergedToolsFiltered(allowed map[string]bool) []mcp.Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var tools []mcp.Tool
	for _, s := range r.servers {
		if allowed[s.ID] {
			tools = append(tools, prefixedActiveTools(s.ToolPrefix, s.Tools)...)
		}
	}
	return tools
}

// MergedToolsFilteredWithTools returns tools from allowed servers, further filtered
// by per-server tool whitelist. If allowedTools is nil or a server has no entry,
// all tools from that server are included. Tool names are returned with prefixes applied.
func (r *Registry) MergedToolsFilteredWithTools(allowed map[string]bool, allowedTools map[string]map[string]bool) []mcp.Tool {
	if allowedTools == nil {
		return r.MergedToolsFiltered(allowed)
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	var tools []mcp.Tool
	for _, s := range r.servers {
		if !allowed[s.ID] {
			continue
		}
		serverToolSet := allowedTools[s.ID]
		for _, t := range s.Tools {
			if !t.IsActive {
				continue
			}
			if serverToolSet == nil || serverToolSet[t.Name] {
				tools = append(tools, mcp.Tool{
					Name:        PrefixedToolName(s.ToolPrefix, t.Name),
					Description: t.Description,
					InputSchema: t.InputSchema,
					IsActive:    true,
				})
			}
		}
	}
	return tools
}

// FindByToolFiltered returns the backend owning the tool (matching prefixed name),
// only if it's in the allowed set and the tool is active. Also returns the original unprefixed tool name.
func (r *Registry) FindByToolFiltered(name string, allowed map[string]bool) (*BackendServer, string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		if !allowed[s.ID] {
			continue
		}
		for _, t := range s.Tools {
			if t.IsActive && PrefixedToolName(s.ToolPrefix, t.Name) == name {
				return s, t.Name
			}
		}
	}
	return nil, ""
}

// FindByToolFilteredWithTools returns the backend owning the tool (matching prefixed name),
// only if the server is allowed AND the tool is in the per-server whitelist.
// Also returns the original unprefixed tool name.
func (r *Registry) FindByToolFilteredWithTools(name string, allowed map[string]bool, allowedTools map[string]map[string]bool) (*BackendServer, string) {
	if allowedTools == nil {
		return r.FindByToolFiltered(name, allowed)
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		if !allowed[s.ID] {
			continue
		}
		serverToolSet := allowedTools[s.ID]
		for _, t := range s.Tools {
			if PrefixedToolName(s.ToolPrefix, t.Name) == name {
				if !t.IsActive {
					return nil, "" // tool exists but inactive
				}
				if serverToolSet == nil || serverToolSet[t.Name] {
					return s, t.Name
				}
				return nil, "" // tool exists but not whitelisted
			}
		}
	}
	return nil, ""
}

// MergedResourcesFiltered returns resources from allowed servers only.
func (r *Registry) MergedResourcesFiltered(allowed map[string]bool) []mcp.Resource {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var resources []mcp.Resource
	for _, s := range r.servers {
		if allowed[s.ID] {
			resources = append(resources, s.Resources...)
		}
	}
	return resources
}

// FindByResourceFiltered returns the backend owning the resource, only if allowed.
func (r *Registry) FindByResourceFiltered(uri string, allowed map[string]bool) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		if !allowed[s.ID] {
			continue
		}
		for _, res := range s.Resources {
			if res.URI == uri {
				return s
			}
		}
	}
	return nil
}

// MergedPromptsFiltered returns prompts from allowed servers only.
func (r *Registry) MergedPromptsFiltered(allowed map[string]bool) []mcp.Prompt {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var prompts []mcp.Prompt
	for _, s := range r.servers {
		if allowed[s.ID] {
			prompts = append(prompts, s.Prompts...)
		}
	}
	return prompts
}

// FindByPromptFiltered returns the backend owning the prompt, only if allowed.
func (r *Registry) FindByPromptFiltered(name string, allowed map[string]bool) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		if !allowed[s.ID] {
			continue
		}
		for _, p := range s.Prompts {
			if p.Name == name {
				return s
			}
		}
	}
	return nil
}
