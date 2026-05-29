package app

import (
	"context"
	"log"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/zohodiscover"
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
//
// When the persisted catalog (zoho_import_tools) is empty for a resolved
// row, the adapter performs a one-shot live tools/list probe against the
// row's upstream URL (using the row's decrypted auth headers) and
// persists the result. Subsequent consent renders are served from the
// persisted catalog. The probe is bounded by zohodiscover.DefaultTimeout
// (10s) and is best-effort: any failure logs and returns Configured=false.
type zohoCatalogAdapter struct {
	imports   *repository.ZohoImportRepo
	users     userFinder
	encryptor *crypto.Encryptor
}

func (a *zohoCatalogAdapter) StateForEmail(ctx context.Context, email string) gateway.ZohoCatalogState {
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
		log.Printf("[zoho-diag] ListTools import_id=%s email=%q tool_count=0 — running one-shot live tools/list probe + persist", row.ID, email)
		tools = a.liveDiscoverAndPersist(ctx, row, email)
		if len(tools) == 0 {
			log.Printf("[zoho-diag] live probe import_id=%s email=%q persisted_count=0 — returning Configured=false (upstream tools/list failed or returned empty; check [zoho-discover] logs)", row.ID, email)
			return gateway.ZohoCatalogState{Configured: false}
		}
		log.Printf("[zoho-diag] live probe import_id=%s email=%q persisted_count=%d — Configured=true", row.ID, email, len(tools))
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

// liveDiscoverAndPersist runs a one-shot upstream tools/list probe against
// row.URL with the row's decrypted auth headers and persists the result
// into zoho_import_tools. Returns the freshly persisted slice (possibly
// empty when the upstream is unreachable / mis-auth'd). Best-effort: all
// errors are logged and mapped to an empty slice so the consent path
// stays responsive.
func (a *zohoCatalogAdapter) liveDiscoverAndPersist(ctx context.Context, row *db.ZohoImport, email string) []db.ZohoImportTool {
	if row == nil || row.URL == "" {
		log.Printf("[zoho-diag] liveDiscoverAndPersist skipped: row nil or row.URL empty (email=%q)", email)
		return nil
	}
	tools, err := zohodiscover.FetchTools(ctx, a.encryptor, row)
	if err != nil {
		log.Printf("[zoho-discover] import=%s url=%s email=%q err=%v (consent-path probe)", row.ID, row.URL, email, err)
		return nil
	}
	if _, perr := a.imports.ReplaceTools(row.ID, tools); perr != nil {
		log.Printf("[zoho-discover] import=%s persist err=%v (consent-path probe) — returning fetched tools without persistence", row.ID, perr)
		return tools
	}
	log.Printf("[zoho-discover] import=%s url=%s tools=%d persisted (consent-path probe email=%q)", row.ID, row.URL, len(tools), email)
	return tools
}
