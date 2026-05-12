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

// FindAdminZohoServer returns the single mcp_servers row representing the
// admin's global Zoho upstream: tool_prefix='zoho', template_slug='',
// is_active, and url != selfURL (excludes this service's own row).
// Returns sql.ErrNoRows when no such row exists.
func (q *Queries) FindAdminZohoServer(ctx context.Context, selfURL string) (*ServerRow, error) {
	const query = `
		SELECT id, url, auth_headers, created_by
		FROM mcp_servers
		WHERE tool_prefix = 'zoho'
		  AND template_slug = ''
		  AND is_active = 1
		  AND url <> ?
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query, selfURL)
	out := &ServerRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy); err != nil {
		return nil, err
	}
	return out, nil
}

// IsAdminGranted returns true when there is a server_authorizations row
// granting full access on serverID for the given email (case-insensitive).
func (q *Queries) IsAdminGranted(ctx context.Context, serverID, email string) (bool, error) {
	if serverID == "" || email == "" {
		return false, nil
	}
	const query = `
		SELECT 1
		FROM server_authorizations
		WHERE mcp_server_id = ?
		  AND LOWER(email) = LOWER(?)
		LIMIT 1
	`
	var dummy int
	err := q.db.QueryRowContext(ctx, query, serverID, email).Scan(&dummy)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("server_authorizations: %w", err)
	}
	return true, nil
}

// FindUserZohoImport returns the oldest active mcp_servers row whose
// tool_prefix starts with 'zoho', template_slug is non-empty, and whose
// created_by matches the caller's identity by exact-email OR login-portion.
// When more than one row matches, the oldest by created_at wins.
// Returns sql.ErrNoRows when nothing matches.
func (q *Queries) FindUserZohoImport(ctx context.Context, email, login string) (*ServerRow, error) {
	emailLower := strings.ToLower(email)
	loginLower := strings.ToLower(login)
	if emailLower == "" && loginLower == "" {
		return nil, sql.ErrNoRows
	}

	const query = `
		SELECT id, url, auth_headers, created_by
		FROM mcp_servers
		WHERE template_slug <> ''
		  AND is_active = 1
		  AND LOWER(tool_prefix) LIKE 'zoho%'
		  AND (
		        LOWER(created_by) = ?
		     OR (? <> '' AND LOWER(created_by) LIKE CONCAT(?, '@%'))
		  )
		ORDER BY created_at ASC
		LIMIT 1
	`
	row := q.db.QueryRowContext(ctx, query, emailLower, loginLower, loginLower)
	out := &ServerRow{}
	if err := row.Scan(&out.ID, &out.URL, &out.AuthHeaders, &out.CreatedBy); err != nil {
		return nil, err
	}
	return out, nil
}
