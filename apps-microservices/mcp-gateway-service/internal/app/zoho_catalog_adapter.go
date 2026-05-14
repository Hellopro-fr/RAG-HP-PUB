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
	if a == nil || a.imports == nil || email == "" {
		return gateway.ZohoCatalogState{}
	}

	isAdmin := false
	if a.users != nil {
		user, err := a.users.GetByEmail(email)
		if err != nil {
			log.Printf("[zoho-catalog] user lookup email=%s err=%v — treating as non-admin", email, err)
		} else if user != nil && user.Role == "admin" {
			isAdmin = true
		}
	}

	var row *db.ZohoImport
	var err error
	if isAdmin {
		row, err = a.imports.GetAdmin()
		if err != nil {
			log.Printf("[zoho-catalog] admin lookup err=%v email=%s", err, email)
		}
	} else {
		row, err = a.imports.FindUserImportByEmail(email)
		if err != nil {
			log.Printf("[zoho-catalog] user import lookup email=%s err=%v", email, err)
		}
	}
	if row == nil {
		return gateway.ZohoCatalogState{Configured: false}
	}

	tools, err := a.imports.ListTools(row.ID)
	if err != nil {
		log.Printf("[zoho-catalog] list tools import=%s err=%v", row.ID, err)
		return gateway.ZohoCatalogState{Configured: false}
	}
	if len(tools) == 0 {
		return gateway.ZohoCatalogState{Configured: false}
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
	return gateway.ZohoCatalogState{Tools: out, Configured: true}
}

// zohoStateFetcher bridges *gateway.Gateway to the authserver.ZohoToolsForUser
// interface. Task 2 renamed FetchZohoToolsForUser → FetchZohoStateForUser on
// the Gateway while authserver.ZohoToolsForUser still carries the old
// signature. This shim will be removed in Task 4 when the authserver interface
// is aligned with ZohoServerState.
type zohoStateFetcher struct {
	gw *gateway.Gateway
}

func (z *zohoStateFetcher) FetchZohoToolsForUser(ctx context.Context, email string) map[string][]mcp.Tool {
	states := z.gw.FetchZohoStateForUser(ctx, email)
	if len(states) == 0 {
		return nil
	}
	out := make(map[string][]mcp.Tool, len(states))
	for id, st := range states {
		out[id] = st.Tools
	}
	return out
}
