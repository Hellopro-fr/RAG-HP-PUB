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
	Capabilities  mcp.ServerCapabilities
	Tools         []mcp.Tool
	Resources     []mcp.Resource
	Prompts       []mcp.Prompt
	AuthHeaders   map[string]string // extra headers forwarded to this backend
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

// FindByTool returns the backend that owns the named tool, or nil if not found.
func (r *Registry) FindByTool(name string) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		for _, t := range s.Tools {
			if t.Name == name {
				return s
			}
		}
	}
	return nil
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

// MergedTools returns the combined tool list from all backends.
func (r *Registry) MergedTools() []mcp.Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var tools []mcp.Tool
	for _, s := range r.servers {
		tools = append(tools, s.Tools...)
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

// MergedToolsFiltered returns tools from allowed servers only.
func (r *Registry) MergedToolsFiltered(allowed map[string]bool) []mcp.Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var tools []mcp.Tool
	for _, s := range r.servers {
		if allowed[s.ID] {
			tools = append(tools, s.Tools...)
		}
	}
	return tools
}

// FindByToolFiltered returns the backend owning the tool, only if it's in the allowed set.
func (r *Registry) FindByToolFiltered(name string, allowed map[string]bool) *BackendServer {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, s := range r.servers {
		if !allowed[s.ID] {
			continue
		}
		for _, t := range s.Tools {
			if t.Name == name {
				return s
			}
		}
	}
	return nil
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
