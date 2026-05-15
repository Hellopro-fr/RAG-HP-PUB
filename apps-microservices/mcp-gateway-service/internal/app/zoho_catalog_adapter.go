package app

import (
	"context"
	"log"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
)

// userFinder is the slice of *repository.UserRepo the adapter needs to
// resolve the viewer's role. Defining it as an interface lets unit tests
// substitute an in-memory fake without spinning up GORM.
type userFinder interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}

// zohoCatalogAdapter wraps ZohoImportRepo + UserRepo to satisfy
// gateway.ZohoUserCatalog.
//
// Resolution order:
//   - role == "admin"  → imports.GetAdmin()
//   - role != "admin"  → imports.FindUserImportByEmail(email)
//
// There is no admin-row fallback for non-admin viewers — that was the
// pre-2026-05-14 behavior that leaked admin tools onto every non-admin
// consent screen and is now intentionally removed.
//
// On any UserRepo error, the viewer is treated as non-admin (fail-safe:
// never auto-promote on transient DB errors).
type zohoCatalogAdapter struct {
	imports *repository.ZohoImportRepo
	users   userFinder
}

func (a *zohoCatalogAdapter) StateForEmail(_ context.Context, email string) gateway.ZohoCatalogState {
	if a == nil {
		log.Printf("[zoho-diag] StateForEmail: adapter is nil — returning empty state")
		return gateway.ZohoCatalogState{}
	}
	if a.imports == nil {
		log.Printf("[zoho-diag] StateForEmail email=%q: imports repo is nil — returning empty state", email)
		return gateway.ZohoCatalogState{}
	}
	if email == "" {
		log.Printf("[zoho-diag] StateForEmail: email is empty — returning empty state (no Configured flag set)")
		return gateway.ZohoCatalogState{}
	}

	log.Printf("[zoho-diag] StateForEmail entry email=%q users_finder_wired=%t", email, a.users != nil)

	isAdmin := false
	if a.users != nil {
		user, err := a.users.GetByEmail(email)
		switch {
		case err != nil:
			log.Printf("[zoho-diag] gateway_users lookup email=%q err=%v — treating as non-admin (fail-safe)", email, err)
		case user == nil:
			log.Printf("[zoho-diag] gateway_users lookup email=%q result=NO_ROW — treating as non-admin (user not in gateway_users)", email)
		case user.Role == "admin":
			log.Printf("[zoho-diag] gateway_users lookup email=%q result=ADMIN (role=%q) — will consult admin zoho row", email, user.Role)
			isAdmin = true
		default:
			log.Printf("[zoho-diag] gateway_users lookup email=%q result=NON_ADMIN role=%q (literal 'admin' required) — will consult per-user zoho row", email, user.Role)
		}
	} else {
		log.Printf("[zoho-diag] users finder not wired email=%q — defaulting to non-admin path", email)
	}

	var row *db.ZohoImport
	var err error
	if isAdmin {
		row, err = a.imports.GetAdmin()
		if err != nil {
			log.Printf("[zoho-diag] GetAdmin email=%q err=%v — returning Configured=false", email, err)
			return gateway.ZohoCatalogState{Configured: false}
		}
		if row == nil {
			log.Printf("[zoho-diag] GetAdmin email=%q result=NO_ROW (no active is_admin=1 row in zoho_imports) — returning Configured=false", email)
			return gateway.ZohoCatalogState{Configured: false}
		}
		log.Printf("[zoho-diag] GetAdmin email=%q result=HIT row_id=%s url=%s is_active=%t", email, row.ID, row.URL, row.IsActive)
	} else {
		row, err = a.imports.FindUserImportByEmail(email)
		if err != nil {
			log.Printf("[zoho-diag] FindUserImportByEmail email=%q err=%v — returning Configured=false", email, err)
			return gateway.ZohoCatalogState{Configured: false}
		}
		if row == nil {
			log.Printf("[zoho-diag] FindUserImportByEmail email=%q result=NO_ROW (no active is_admin=0 row with LOWER(created_by)=LOWER(email)) — returning Configured=false. Hint: check zoho_imports.created_by exact match (no login-portion fallback in consent path).", email)
			return gateway.ZohoCatalogState{Configured: false}
		}
		log.Printf("[zoho-diag] FindUserImportByEmail email=%q result=HIT row_id=%s created_by=%q url=%s is_active=%t", email, row.ID, row.CreatedBy, row.URL, row.IsActive)
	}

	tools, err := a.imports.ListTools(row.ID)
	if err != nil {
		log.Printf("[zoho-diag] ListTools import_id=%s email=%q err=%v — returning Configured=false", row.ID, email, err)
		return gateway.ZohoCatalogState{Configured: false}
	}
	if len(tools) == 0 {
		log.Printf("[zoho-diag] ListTools import_id=%s email=%q tool_count=0 — returning Configured=false. Hint: discovery never persisted any tool (upstream tools/list failed or returned empty). Trigger POST /api/v1/zoho-imports/%s/discover and watch [zoho-discover] logs.", row.ID, email, row.ID)
		return gateway.ZohoCatalogState{Configured: false}
	}

	log.Printf("[zoho-diag] StateForEmail email=%q result=Configured=true import_id=%s tool_count=%d", email, row.ID, len(tools))

	out := make([]mcp.Tool, 0, len(tools))
	for _, t := range tools {
		out = append(out, mcp.Tool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    true,
		})
	}
	return gateway.ZohoCatalogState{Tools: out, Configured: true}
}

