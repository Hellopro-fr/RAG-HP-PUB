// Package zohodiscover probes an upstream Zoho MCP server for its current
// tools/list catalog and shapes the result into db.ZohoImportTool rows ready
// for persistence in zoho_import_tools.
//
// Two callers share the helper:
//   - api.discoverZohoToolsForImport — runs at row create / admin upsert /
//     manual /discover / successful /test.
//   - app.zohoCatalogAdapter — runs at consent-screen render when the
//     persisted catalog is empty, so the first viewer triggers a probe and
//     the result is persisted for every subsequent render.
package zohodiscover

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
)

// DefaultTimeout caps each upstream tools/list probe.
const DefaultTimeout = 10 * time.Second

// FetchTools POSTs a JSON-RPC tools/list to row.URL with the decrypted
// auth headers and returns the parsed catalog. Errors are terminal for
// this call; callers log and decide how to handle (keep previous, return
// Configured=false, etc.).
func FetchTools(ctx context.Context, encryptor *crypto.Encryptor, row *db.ZohoImport) ([]db.ZohoImportTool, error) {
	headers := DecryptAuthHeaders(encryptor, row.AuthHeaders)

	const probeBody = `{"jsonrpc":"2.0","method":"tools/list","id":1}`
	reqCtx, cancel := context.WithTimeout(ctx, DefaultTimeout)
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

	return ParseToolsListResponse(body)
}

// DecryptAuthHeaders returns the {k:v} header map persisted for a Zoho row.
// Always returns a non-nil map. Errors are silently mapped to an empty map.
func DecryptAuthHeaders(encryptor *crypto.Encryptor, raw []byte) map[string]string {
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

// ParseToolsListResponse decodes a JSON-RPC tools/list envelope.
func ParseToolsListResponse(body []byte) ([]db.ZohoImportTool, error) {
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
