package api

import (
	"context"
	"log"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/zohodiscover"
)

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

	tools, err := zohodiscover.FetchTools(ctx, encryptor, row)
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

// fetchZohoTools is a thin wrapper retained so zoho_admin_handlers.go and
// existing tests keep their call sites. New code should call
// zohodiscover.FetchTools directly.
func fetchZohoTools(ctx context.Context, encryptor *crypto.Encryptor, row *db.ZohoImport) ([]db.ZohoImportTool, error) {
	return zohodiscover.FetchTools(ctx, encryptor, row)
}

// decryptZohoAuthHeaders wrapper kept for test compatibility.
func decryptZohoAuthHeaders(encryptor *crypto.Encryptor, raw []byte) map[string]string {
	return zohodiscover.DecryptAuthHeaders(encryptor, raw)
}

// parseToolsListResponse wrapper kept for test compatibility.
func parseToolsListResponse(body []byte) ([]db.ZohoImportTool, error) {
	return zohodiscover.ParseToolsListResponse(body)
}
