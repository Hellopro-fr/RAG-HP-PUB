package api

import (
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// LLMInstructionRowRequest is one row inside a create/update body. Kind is
// "per_server" (default) or "general" — general rows ignore server_ids and
// always render.
type LLMInstructionRowRequest struct {
	ID        string   `json:"id,omitempty"` // preserved on update; empty = new row
	Kind      string   `json:"kind,omitempty"`
	Title     string   `json:"title,omitempty"`
	Body      string   `json:"body"`
	ServerIDs []string `json:"server_ids"`
}

// LLMInstructionRowResponse is the wire shape of a single row.
type LLMInstructionRowResponse struct {
	ID           string   `json:"id"`
	Kind         string   `json:"kind"`
	Title        string   `json:"title,omitempty"`
	Body         string   `json:"body"`
	ServerIDs    []string `json:"server_ids"`
	DisplayOrder int      `json:"display_order"`
}

// LLMInstructionResponse is the wire format for an instruction page. Rows are
// ordered by display_order; server_ids per row preserve the authoring choice
// so the frontend builder can round-trip edits cleanly.
type LLMInstructionResponse struct {
	ID          string                      `json:"id"`
	Title       string                      `json:"title"`
	Description string                      `json:"description,omitempty"`
	Rows        []LLMInstructionRowResponse `json:"rows"`
	CreatedBy   string                      `json:"created_by,omitempty"`
	CreatedAt   string                      `json:"created_at"`
	UpdatedAt   string                      `json:"updated_at"`
}

// CreateLLMInstructionRequest is the body for POST /api/v1/llm-instructions.
type CreateLLMInstructionRequest struct {
	Title       string                     `json:"title"`
	Description string                     `json:"description,omitempty"`
	Rows        []LLMInstructionRowRequest `json:"rows"`
}

// UpdateLLMInstructionRequest is the body for PUT /api/v1/llm-instructions/{id}.
// Rows, when provided, replace the previous set atomically. Pointer-only fields
// let the handler distinguish "field omitted" from "field set to zero value".
type UpdateLLMInstructionRequest struct {
	Title       *string                    `json:"title,omitempty"`
	Description *string                    `json:"description,omitempty"`
	Rows        []LLMInstructionRowRequest `json:"rows,omitempty"`
	RowsProvided bool                      `json:"-"`
}

// LLMInstructionUsageResponse lists the tokens and OAuth2 clients that
// currently reference an instruction — shown on the admin edit page so the
// operator knows the blast radius of a change.
type LLMInstructionUsageResponse struct {
	TokenIDs        []string `json:"token_ids"`
	OAuth2ClientIDs []string `json:"oauth2_client_ids"`
}

// LLMInstructionRenderedResponse is the server-composed Markdown preview the
// admin UI shows — mirrors exactly the bytes the gateway would inject into
// MCP `initialize.instructions` for a session that has every row's scope
// available. No server filtering is applied here; it's a "what the page can
// produce" view, not a "what a specific token would see".
type LLMInstructionRenderedResponse struct {
	Markdown string `json:"markdown"`
}

// toLLMInstructionResponse converts a GORM row into the wire format. Rows is
// always a non-nil slice so clients can blindly iterate without guarding for
// null JSON.
func toLLMInstructionResponse(ins *db.LLMInstruction) LLMInstructionResponse {
	rows := make([]LLMInstructionRowResponse, 0, len(ins.Rows))
	for _, r := range ins.Rows {
		serverIDs := make([]string, 0, len(r.Servers))
		for _, s := range r.Servers {
			serverIDs = append(serverIDs, s.ServerID)
		}
		kind := r.Kind
		if kind == "" {
			// Backward-compat for rows written before the Kind column existed.
			kind = db.LLMInstructionRowKindPerServer
		}
		rows = append(rows, LLMInstructionRowResponse{
			ID:           r.ID,
			Kind:         kind,
			Title:        r.Title,
			Body:         r.Body,
			ServerIDs:    serverIDs,
			DisplayOrder: r.DisplayOrder,
		})
	}
	return LLMInstructionResponse{
		ID:          ins.ID,
		Title:       ins.Title,
		Description: ins.Description,
		Rows:        rows,
		CreatedBy:   ins.CreatedBy,
		CreatedAt:   ins.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:   ins.UpdatedAt.UTC().Format(time.RFC3339),
	}
}
