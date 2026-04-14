package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/urlvalidation"
)

// ── Import .mcp.json ─────────────────────────────────────────────────────────

// mcpJSONEntry represents a single server entry in .mcp.json.
// The format is flexible — all fields are optional to cover every variant.
type mcpJSONEntry struct {
	// Remote transports (http / sse)
	URL       string            `json:"url,omitempty"`
	Transport string            `json:"transport,omitempty"` // "sse", "http", "streamable-http"
	Headers   map[string]string `json:"headers,omitempty"`

	// stdio transport
	Command string            `json:"command,omitempty"`
	Args    []string          `json:"args,omitempty"`
	Env     map[string]string `json:"env,omitempty"`

	// Claude Code / Cursor shorthand (type field)
	Type string `json:"type,omitempty"` // "sse", "http", "stdio"

	// Cline format extras
	Disabled          *bool  `json:"disabled,omitempty"`
	AutoApprove       []string `json:"autoApprove,omitempty"`
	AlwaysAllow       []string `json:"alwaysAllow,omitempty"`
	Timeout           *uint  `json:"timeout,omitempty"`
}

// importRequest wraps the various .mcp.json formats.
type importRequest struct {
	// Standard format: { "mcpServers": { "name": {...} } }
	MCPServers map[string]mcpJSONEntry `json:"mcpServers,omitempty"`

	// Flat format: { "name": {...} } — if mcpServers is absent we try top-level
	// Handled via custom unmarshal logic below.
}

type importResultEntry struct {
	Name   string `json:"name"`
	ID     string `json:"id,omitempty"`
	Status string `json:"status"` // "created", "skipped", "error"
	Error  string `json:"error,omitempty"`
}

type importResponse struct {
	Imported int                 `json:"imported"`
	Skipped  int                 `json:"skipped"`
	Errors   int                 `json:"errors"`
	Results  []importResultEntry `json:"results"`
}

func (h *Handler) handleImportMCPJSON(w http.ResponseWriter, r *http.Request) {
	// Parse as generic JSON to handle all formats
	var raw map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}

	entries := h.parseMCPJSON(raw)
	if len(entries) == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "no MCP server entries found in JSON"})
		return
	}

	autoDiscover := r.URL.Query().Get("auto_discover") != "false"
	resp := importResponse{Results: make([]importResultEntry, 0, len(entries))}

	for name, entry := range entries {
		result := h.importSingleEntry(r, name, entry, autoDiscover)
		switch result.Status {
		case "created":
			resp.Imported++
		case "skipped":
			resp.Skipped++
		default:
			resp.Errors++
		}
		resp.Results = append(resp.Results, result)
	}

	writeJSON(w, http.StatusOK, resp)
}

// parseMCPJSON extracts server entries from all known .mcp.json variants.
func (h *Handler) parseMCPJSON(raw map[string]json.RawMessage) map[string]mcpJSONEntry {
	entries := make(map[string]mcpJSONEntry)

	// Try standard format: { "mcpServers": { ... } }
	if serversRaw, ok := raw["mcpServers"]; ok {
		var servers map[string]mcpJSONEntry
		if json.Unmarshal(serversRaw, &servers) == nil && len(servers) > 0 {
			return servers
		}
	}

	// Try Claude Desktop format: { "mcpServers": [...] } (array — unlikely but handle)
	if serversRaw, ok := raw["mcpServers"]; ok {
		var arr []mcpJSONEntry
		if json.Unmarshal(serversRaw, &arr) == nil {
			for i, e := range arr {
				name := fmt.Sprintf("server-%d", i+1)
				if e.Command != "" {
					name = e.Command
				}
				entries[name] = e
			}
			if len(entries) > 0 {
				return entries
			}
		}
	}

	// Try Windsurf / other: { "serverName": { ... } } at top level
	// Each top-level key that is an object with url/command is treated as a server
	for key, val := range raw {
		if key == "mcpServers" {
			continue
		}
		var entry mcpJSONEntry
		if json.Unmarshal(val, &entry) == nil && (entry.URL != "" || entry.Command != "") {
			entries[key] = entry
		}
	}

	return entries
}

// importSingleEntry processes one server entry and creates it in the DB.
func (h *Handler) importSingleEntry(r *http.Request, name string, entry mcpJSONEntry, autoDiscover bool) importResultEntry {
	result := importResultEntry{Name: name}

	// Resolve the actual URL and transport from the entry
	serverURL, mcpTransport, mcpCommand, mcpArgs, mcpEnv, mcpHeaders := resolveEntry(entry)

	if serverURL == "" && mcpCommand == "" {
		result.Status = "error"
		result.Error = "could not determine server URL or command"
		return result
	}

	// SSRF protection: validate remote server URLs
	if serverURL != "" {
		if err := urlvalidation.ValidateServerURL(serverURL, h.allowInternalURLs); err != nil {
			result.Status = "error"
			result.Error = "invalid server URL: " + err.Error()
			return result
		}
	}

	// Use URL or synthesize one for stdio
	dbURL := serverURL
	if dbURL == "" {
		dbURL = "stdio://" + mcpCommand
	}

	// Check for duplicate URL (check across all users)
	existing, _ := h.repo.ListAll(nil, "", "")
	for _, s := range existing {
		if s.URL == dbURL || s.Name == name {
			result.Status = "skipped"
			result.Error = fmt.Sprintf("server already exists (id: %s)", s.ID)
			result.ID = s.ID
			return result
		}
	}

	id := uuid.New().String()
	srv := db.MCPServer{
		ID:                  id,
		Name:                name,
		URL:                 strings.TrimRight(dbURL, "/"),
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		MCPTransport:        mcpTransport,
		MCPCommand:          mcpCommand,
		DocSlug:             generateDocSlug(name, id),
		CreatedBy:           auth.UserEmailFromContext(r.Context()),
	}

	if entry.Disabled != nil && *entry.Disabled {
		srv.IsActive = false
	}
	if entry.Timeout != nil && *entry.Timeout > 0 {
		srv.ConnectTimeoutMs = *entry.Timeout
	}
	if len(mcpArgs) > 0 {
		srv.MCPArgs, _ = json.Marshal(mcpArgs)
	}
	if len(mcpEnv) > 0 {
		srv.MCPEnv, _ = json.Marshal(mcpEnv)
	}
	// Merge imported headers into auth_headers (encrypted at rest)
	if len(mcpHeaders) > 0 {
		b, _ := json.Marshal(mcpHeaders)
		srv.AuthHeaders = b
	}

	if err := h.repo.Create(&srv); err != nil {
		if strings.Contains(err.Error(), "Duplicate") {
			result.Status = "skipped"
			result.Error = "duplicate URL"
			return result
		}
		result.Status = "error"
		result.Error = err.Error()
		return result
	}

	result.ID = id
	result.Status = "created"

	// Auto-discover for remote servers only
	// Use mcpHeaders directly because repo.Create() encrypted srv.AuthHeaders in-place
	if autoDiscover && mcpTransport != "stdio" && serverURL != "" {
		if err := h.gw.DiscoverAndRegister(r.Context(), id, srv.URL, mcpHeaders); err != nil {
			log.Printf("[api] import auto-discover failed for %s (%s): %v", name, srv.URL, err)
			_ = h.repo.UpdateHealth(id, "unhealthy", err.Error())
		} else {
			if backend := h.registry.FindByID(id); backend != nil {
				h.saveBackendCapabilities(id, backend)
			}
		}
	}

	return result
}

// resolveEntry analyzes the entry and extracts the canonical fields.
// It handles mcp-remote wrappers, bare URLs, stdio commands, etc.
func resolveEntry(entry mcpJSONEntry) (url, mcpTransport, mcpCommand string, mcpArgs []string, mcpEnv, mcpHeaders map[string]string) {
	mcpHeaders = entry.Headers
	mcpEnv = entry.Env

	// Determine transport from explicit fields
	transport := entry.Transport
	if transport == "" {
		transport = entry.Type
	}

	// Case 1: URL-based (http / sse)
	if entry.URL != "" {
		url = strings.TrimRight(entry.URL, "/")
		switch strings.ToLower(transport) {
		case "sse":
			mcpTransport = "sse"
		default:
			mcpTransport = "http"
		}
		return
	}

	// Case 2: command-based (stdio or mcp-remote wrapper)
	if entry.Command != "" {
		// Check if this is an mcp-remote wrapper: { "command": "npx", "args": ["-y", "mcp-remote", "http://..."] }
		if isRemoteWrapper(entry.Command, entry.Args) {
			extractedURL, extractedTransport := extractURLFromRemoteArgs(entry.Args)
			if extractedURL != "" {
				url = strings.TrimRight(extractedURL, "/")
				mcpTransport = extractedTransport
				// Store the original command/args for MCP JSON generation
				mcpCommand = entry.Command
				mcpArgs = entry.Args
				return
			}
		}

		// Check for supergateway pattern: { "command": "npx", "args": ["-y", "supergateway", "--sse", "http://..."] }
		if isSupergateway(entry.Command, entry.Args) {
			extractedURL := extractURLFromSupergatewayArgs(entry.Args)
			if extractedURL != "" {
				url = strings.TrimRight(extractedURL, "/")
				mcpTransport = "sse"
				mcpCommand = entry.Command
				mcpArgs = entry.Args
				return
			}
		}

		// Pure stdio server
		mcpTransport = "stdio"
		mcpCommand = entry.Command
		mcpArgs = entry.Args
		url = "" // no URL for pure stdio
		return
	}

	return
}

// isRemoteWrapper detects mcp-remote patterns in args.
func isRemoteWrapper(command string, args []string) bool {
	for _, arg := range args {
		if arg == "mcp-remote" || strings.HasSuffix(arg, "/mcp-remote") {
			return true
		}
	}
	// Also detect: command = "mcp-remote"
	if command == "mcp-remote" {
		return true
	}
	return false
}

// extractURLFromRemoteArgs finds the URL in mcp-remote arguments.
// Patterns:
//   npx -y mcp-remote http://host:port/mcp --allow-http
//   mcp-remote http://host:port/sse
//   npx mcp-remote http://host:port/mcp --header "Authorization: Bearer xxx"
func extractURLFromRemoteArgs(args []string) (string, string) {
	transport := "http"
	for _, arg := range args {
		if strings.HasPrefix(arg, "http://") || strings.HasPrefix(arg, "https://") {
			// Determine transport from URL path
			if strings.HasSuffix(arg, "/sse") || strings.Contains(arg, "/sse?") {
				transport = "sse"
			}
			return arg, transport
		}
	}
	return "", ""
}

// isSupergateway detects supergateway patterns.
func isSupergateway(command string, args []string) bool {
	if command == "supergateway" {
		return true
	}
	for _, arg := range args {
		if arg == "supergateway" {
			return true
		}
	}
	return false
}

// extractURLFromSupergatewayArgs finds the URL in supergateway arguments.
// Pattern: supergateway --sse http://host:port/sse --port 8080
func extractURLFromSupergatewayArgs(args []string) string {
	for i, arg := range args {
		if (arg == "--sse" || arg == "--url") && i+1 < len(args) {
			return args[i+1]
		}
		if strings.HasPrefix(arg, "http://") || strings.HasPrefix(arg, "https://") {
			return arg
		}
	}
	return ""
}
