package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

// zohoDiscoverTimeout caps each upstream tools/list probe. Mirrors the
// timeout used by the manual /test endpoint so behaviour stays consistent.
const zohoDiscoverTimeout = 10 * time.Second

// discoverZohoToolsForImport fetches the current tool catalog from the
// upstream MCP server pointed at by row.URL using the row's decrypted
// auth headers, then atomically replaces the persisted catalog via
// repo.ReplaceTools. Best-effort: every failure is logged and swallowed
// so the caller (sheet import, admin upsert, test endpoint) doesn't fail
// the user-facing operation because of an upstream hiccup.
func discoverZohoToolsForImport(
	ctx context.Context,
	repo *repository.ZohoImportRepo,
	encryptor *crypto.Encryptor,
	row *db.ZohoImport,
) {
	if repo == nil || row == nil || row.ID == "" || row.URL == "" {
		return
	}

	tools, err := fetchZohoTools(ctx, encryptor, row)
	if err != nil {
		log.Printf("[zoho-discover] import=%s url=%s err=%v — keeping previous catalog", row.ID, row.URL, err)
		return
	}

	if _, err := repo.ReplaceTools(row.ID, tools); err != nil {
		log.Printf("[zoho-discover] import=%s persist err=%v", row.ID, err)
		return
	}
	log.Printf("[zoho-discover] import=%s url=%s tools=%d persisted", row.ID, row.URL, len(tools))
}

// fetchZohoTools POSTs a JSON-RPC tools/list to the upstream URL with the
// decrypted auth headers and returns the parsed catalog. Errors here are
// terminal for this call but never reach the user — the caller logs and
// keeps the previously persisted catalog.
func fetchZohoTools(ctx context.Context, encryptor *crypto.Encryptor, row *db.ZohoImport) ([]db.ZohoImportTool, error) {
	headers := decryptZohoAuthHeaders(encryptor, row.AuthHeaders)

	const probeBody = `{"jsonrpc":"2.0","method":"tools/list","id":1}`
	reqCtx, cancel := context.WithTimeout(ctx, zohoDiscoverTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(reqCtx, http.MethodPost, row.URL, bytes.NewBufferString(probeBody))
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 400 {
		return nil, fmt.Errorf("upstream status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	return parseToolsListResponse(body)
}

// decryptZohoAuthHeaders returns the {k:v} header map persisted for a Zoho
// row. Always returns a non-nil map so callers can range over it without a
// nil check. Errors are silently mapped to an empty map — same as the
// existing test endpoint behaviour.
func decryptZohoAuthHeaders(encryptor *crypto.Encryptor, raw []byte) map[string]string {
	headers := map[string]string{}
	if len(raw) == 0 {
		return headers
	}
	if encryptor != nil {
		pt, err := encryptor.Decrypt(raw)
		if err != nil {
			return headers
		}
		_ = json.Unmarshal(pt, &headers)
		return headers
	}
	_ = json.Unmarshal(raw, &headers)
	return headers
}

// parseToolsListResponse decodes a JSON-RPC tools/list envelope. Missing
// or error responses yield an empty slice (no error) — the caller logs
// the upstream status separately.
func parseToolsListResponse(body []byte) ([]db.ZohoImportTool, error) {
	var envelope struct {
		Result struct {
			Tools []struct {
				Name        string          `json:"name"`
				Description string          `json:"description"`
				InputSchema json.RawMessage `json:"inputSchema"`
			} `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	out := make([]db.ZohoImportTool, 0, len(envelope.Result.Tools))
	for _, t := range envelope.Result.Tools {
		schema := t.InputSchema
		if len(schema) == 0 {
			schema = json.RawMessage(`{}`)
		}
		out = append(out, db.ZohoImportTool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: schema,
		})
	}
	return out, nil
}
