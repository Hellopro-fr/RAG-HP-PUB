package db

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
)

// Queries wraps a *sql.DB with the prepared statements the resolver needs.
type Queries struct {
	db *sql.DB
}

// NewQueries returns a Queries primed with the given DB handle.
func NewQueries(db *sql.DB) *Queries {
	return &Queries{db: db}
}

// FindAdminZohoImport returns the singleton admin row from zoho_imports.
// Returns sql.ErrNoRows when no admin row is configured.
func (q *Queries) FindAdminZohoImport(ctx context.Context) (*ImportRow, error) {
	const query = `
		SELECT id, url, auth_headers, created_by, is_admin
		FROM zoho_imports
		WHERE is_admin = 1 AND is_active = 1
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query)
	out := &ImportRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy, &out.IsAdmin); err != nil {
		return nil, err
	}
	return out, nil
}

// IsAdminGranted returns true when a server_authorizations row grants
// full access on stubServerID for the given email (case-insensitive).
// stubServerID is the UUID of the mcp_servers row whose tool_prefix='zoho'
// and url points at this service (configured via ZOHO_STUB_SERVER_ID).
func (q *Queries) IsAdminGranted(ctx context.Context, stubServerID, email string) (bool, error) {
	if stubServerID == "" || email == "" {
		return false, nil
	}
	const query = `
		SELECT 1
		FROM server_authorizations
		WHERE server_id = ?
		  AND LOWER(email) = LOWER(?)
		LIMIT 1
	`
	var dummy int
	err := q.db.QueryRowContext(ctx, query, stubServerID, email).Scan(&dummy)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("server_authorizations: %w", err)
	}
	return true, nil
}

// FindUserZohoImport returns the oldest active per-user zoho_imports row
// whose created_by matches by exact email or by login-portion.
// Returns sql.ErrNoRows when nothing matches.
func (q *Queries) FindUserZohoImport(ctx context.Context, email, login string) (*ImportRow, error) {
	emailLower := strings.ToLower(email)
	loginLower := strings.ToLower(login)
	if emailLower == "" && loginLower == "" {
		return nil, sql.ErrNoRows
	}

	const query = `
		SELECT id, url, auth_headers, created_by, is_admin
		FROM zoho_imports
		WHERE is_admin = 0 AND is_active = 1
		  AND (
		        LOWER(created_by) = ?
		     OR (? <> '' AND LOWER(created_by) = ?)
		     OR (? <> '' AND LOWER(created_by) LIKE CONCAT(?, '@%'))
		  )
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query, emailLower, loginLower, loginLower, loginLower, loginLower)
	out := &ImportRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy, &out.IsAdmin); err != nil {
		return nil, err
	}
	return out, nil
}
