package auth

import (
	"bytes"
	"io"
	"log"
	"net/http"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

const auditChannelBuffer = 256
const auditMaxBodyBytes = 10 * 1024 // 10 KB

// AuditMiddleware records API actions asynchronously.
type AuditMiddleware struct {
	repo *repository.AuditRepo
	ch   chan *db.AuditLog
}

// NewAuditMiddleware creates an AuditMiddleware and starts the background writer goroutine.
func NewAuditMiddleware(repo *repository.AuditRepo) *AuditMiddleware {
	m := &AuditMiddleware{
		repo: repo,
		ch:   make(chan *db.AuditLog, auditChannelBuffer),
	}
	go m.writer()
	return m
}

// writer reads from the channel and persists each entry.
func (m *AuditMiddleware) writer() {
	for entry := range m.ch {
		if err := m.repo.Insert(entry); err != nil {
			log.Printf("[audit] failed to insert audit log: %v", err)
		}
	}
}

// responseCapture wraps http.ResponseWriter to capture the status code and
// response body for error responses (status >= 400).
type responseCapture struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (rc *responseCapture) WriteHeader(status int) {
	rc.status = status
	rc.ResponseWriter.WriteHeader(status)
}

func (rc *responseCapture) Write(b []byte) (int, error) {
	if rc.status >= 400 {
		rc.body.Write(b)
	}
	return rc.ResponseWriter.Write(b)
}

// Wrap returns an http.Handler that audits qualifying requests.
//
// Logged requests:
//   - Write operations (POST/PUT/DELETE) on /api/
//   - Failed reads (GET returning 4xx/5xx) on /api/
//   - MCP transport paths (/mcp, /sse, /message)
func (m *AuditMiddleware) Wrap(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		method := r.Method

		isMCPTransport := strings.HasPrefix(path, "/mcp") || strings.HasPrefix(path, "/sse") || strings.HasPrefix(path, "/message")
		isAPIWrite := strings.HasPrefix(path, "/api/") && (method == http.MethodPost || method == http.MethodPut || method == http.MethodDelete)
		isAPIRead := strings.HasPrefix(path, "/api/") && method == http.MethodGet

		shouldAudit := isMCPTransport || isAPIWrite || isAPIRead

		if !shouldAudit {
			next.ServeHTTP(w, r)
			return
		}

		// Read request body for write operations (capped at 10 KB).
		var requestBody string
		if isAPIWrite && r.Body != nil {
			raw, _ := io.ReadAll(io.LimitReader(r.Body, auditMaxBodyBytes))
			r.Body = io.NopCloser(bytes.NewReader(raw))
			requestBody = sanitizeBody(string(raw))
		}

		// Capture response.
		rc := &responseCapture{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rc, r)

		// Only log failed reads; always log writes and MCP.
		if isAPIRead && rc.status < 400 {
			return
		}

		action, resourceType, resourceID := classifyRequest(method, path)

		entry := &db.AuditLog{
			UserEmail:      UserEmailFromContext(r.Context()),
			Action:         action,
			ResourceType:   resourceType,
			ResourceID:     resourceID,
			RequestMethod:  method,
			RequestPath:    path,
			RequestBody:    requestBody,
			ResponseStatus: rc.status,
			IPAddress:      extractIP(r),
		}
		if rc.status >= 400 {
			entry.ResponseBody = rc.body.String()
		}

		select {
		case m.ch <- entry:
		default:
			log.Printf("[audit] channel full — dropping audit entry for %s %s", method, path)
		}
	})
}

// sanitizeBody redacts common sensitive field values in a JSON body string.
func sanitizeBody(body string) string {
	sensitive := []string{"password", "secret", "token", "client_secret", "authorization", "auth_headers"}
	for _, key := range sensitive {
		// Simple approach: redact value after "key": "..."
		for _, quote := range []string{`"` + key + `":`, `"` + key + `" :`} {
			if idx := strings.Index(strings.ToLower(body), strings.ToLower(quote)); idx != -1 {
				start := idx + len(quote)
				// Skip whitespace
				for start < len(body) && (body[start] == ' ' || body[start] == '\t') {
					start++
				}
				if start < len(body) && body[start] == '"' {
					// Find closing quote
					end := strings.Index(body[start+1:], `"`)
					if end != -1 {
						body = body[:start+1] + "***" + body[start+1+end:]
					}
				}
			}
		}
	}
	return body
}

// classifyRequest maps a method + path to (action, resourceType, resourceID).
func classifyRequest(method, path string) (action, resourceType, resourceID string) {
	// Normalize path: strip /api/v1/ prefix for classification
	trimmed := strings.TrimPrefix(path, "/api/v1/")

	parts := strings.SplitN(trimmed, "/", 3)
	if len(parts) == 0 {
		return method, "", ""
	}
	resourceType = parts[0]

	switch method {
	case http.MethodGet:
		action = "read"
	case http.MethodPost:
		action = "create"
	case http.MethodPut:
		action = "update"
	case http.MethodDelete:
		action = "delete"
	default:
		action = strings.ToLower(method)
	}

	if len(parts) >= 2 && parts[1] != "" {
		resourceID = parts[1]
		// For sub-actions like /servers/{id}/enable, include the action suffix
		if len(parts) == 3 && parts[2] != "" {
			action = action + "." + parts[2]
		}
	}

	// MCP transport paths
	if strings.HasPrefix(path, "/mcp") || strings.HasPrefix(path, "/sse") || strings.HasPrefix(path, "/message") {
		resourceType = "mcp"
		action = "mcp." + strings.ToLower(method)
	}

	return action, resourceType, resourceID
}

// extractIP extracts the client IP address from the request.
// Priority: X-Forwarded-For → X-Real-IP → RemoteAddr.
func extractIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		// X-Forwarded-For may contain a comma-separated list; take the first entry.
		parts := strings.SplitN(xff, ",", 2)
		return strings.TrimSpace(parts[0])
	}
	if xri := r.Header.Get("X-Real-IP"); xri != "" {
		return xri
	}
	// Strip port from RemoteAddr.
	addr := r.RemoteAddr
	if idx := strings.LastIndex(addr, ":"); idx != -1 {
		return addr[:idx]
	}
	return addr
}
