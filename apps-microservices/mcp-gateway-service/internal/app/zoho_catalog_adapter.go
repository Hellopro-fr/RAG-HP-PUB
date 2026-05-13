package app

import (
	"context"
	"log"

	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
)

// zohoCatalogAdapter wraps ZohoImportRepo to satisfy gateway.ZohoUserCatalog.
// Resolution order: caller's email → per-user import row → admin row.
// Whichever row resolves, the persisted tool catalog (zoho_import_tools)
// is returned. Empty slice when nothing resolves so the gateway can decide
// whether to fall back to the registry's cached admin tools.
type zohoCatalogAdapter struct {
	imports *repository.ZohoImportRepo
}

func (a *zohoCatalogAdapter) ToolsForEmail(_ context.Context, email string) []mcp.Tool {
	if a == nil || a.imports == nil || email == "" {
		return nil
	}

	row, err := a.imports.FindUserImportByEmail(email)
	if err != nil {
		log.Printf("[zoho-catalog] lookup user email=%s err=%v", email, err)
	}
	if row == nil {
		adminRow, aerr := a.imports.GetAdmin()
		if aerr != nil {
			log.Printf("[zoho-catalog] no user row + admin lookup err=%v email=%s", aerr, email)
			return nil
		}
		row = adminRow
	}
	if row == nil {
		return nil
	}

	tools, err := a.imports.ListTools(row.ID)
	if err != nil {
		log.Printf("[zoho-catalog] list tools import=%s err=%v", row.ID, err)
		return nil
	}
	out := make([]mcp.Tool, 0, len(tools))
	for _, t := range tools {
		out = append(out, mcp.Tool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    true,
		})
	}
	return out
}
