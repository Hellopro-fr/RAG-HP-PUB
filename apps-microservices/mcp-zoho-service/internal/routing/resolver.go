package routing

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	"mcp-zoho-service/internal/db"
)

// Sentinel errors surfaced as JSON-RPC envelopes by the transport layer.
var (
	ErrNoZohoConfigured = errors.New("no_zoho_configured")
	ErrMisconfigured    = errors.New("misconfigured")
	ErrInvalidIdentity  = errors.New("invalid_identity")
)

// QueryRunner is the narrow contract resolver needs from the DB layer.
type QueryRunner interface {
	FindAdminZohoServer(ctx context.Context, selfURL string) (*db.ServerRow, error)
	IsAdminGranted(ctx context.Context, serverID, email string) (bool, error)
	FindUserZohoImport(ctx context.Context, email, login string) (*db.ServerRow, error)
}

// Decryptor unwraps an encrypted blob (mcp_servers.auth_headers).
type Decryptor interface {
	Decrypt([]byte) ([]byte, error)
}

// Resolver maps a caller's identity to an upstream Zoho URL.
type Resolver struct {
	q       QueryRunner
	dec     Decryptor
	cache   *cache
	selfURL string
}

// NewResolver wires the dependencies.
func NewResolver(q QueryRunner, dec Decryptor, ttl time.Duration, selfURL string) *Resolver {
	return &Resolver{q: q, dec: dec, cache: newCache(ttl), selfURL: selfURL}
}

// Resolve returns the upstream URL and decrypted headers for the caller, or
// one of the sentinel errors above. The cache is consulted first.
func (r *Resolver) Resolve(ctx context.Context, email, login string) (*Resolution, error) {
	if email == "" && login == "" {
		return nil, ErrInvalidIdentity
	}
	key := lower(email)
	if v, ok := r.cache.get(key); ok {
		return v, nil
	}

	admin, err := r.q.FindAdminZohoServer(ctx, r.selfURL)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrMisconfigured
		}
		return nil, fmt.Errorf("find admin row: %w", err)
	}

	granted, err := r.q.IsAdminGranted(ctx, admin.ID, email)
	if err != nil {
		return nil, fmt.Errorf("server_authorizations lookup: %w", err)
	}
	if granted {
		res, err := r.buildResolution(admin)
		if err != nil {
			return nil, err
		}
		r.cache.set(key, res)
		return res, nil
	}

	userRow, err := r.q.FindUserZohoImport(ctx, email, login)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNoZohoConfigured
		}
		return nil, fmt.Errorf("find user row: %w", err)
	}

	// Defensive Go-side match — SQL already filtered, but a future SQL
	// relaxation shouldn't slip through.
	if !matchesUserEmail(userRow.CreatedBy, email, login) {
		log.Printf("[resolver] WARN: SQL match for %s did not pass Go-side matchesUserEmail (created_by=%q)", email, userRow.CreatedBy)
		return nil, ErrNoZohoConfigured
	}

	res, err := r.buildResolution(userRow)
	if err != nil {
		return nil, err
	}
	r.cache.set(key, res)
	return res, nil
}

func (r *Resolver) buildResolution(row *db.ServerRow) (*Resolution, error) {
	headers := map[string]string{}
	if len(row.AuthHeaders) > 0 {
		pt, err := r.dec.Decrypt(row.AuthHeaders)
		if err != nil {
			return nil, fmt.Errorf("decrypt auth_headers for server %s: %w", row.ID, err)
		}
		if err := json.Unmarshal(pt, &headers); err != nil {
			return nil, fmt.Errorf("decode auth_headers for server %s: %w", row.ID, err)
		}
	}
	return &Resolution{UpstreamURL: row.URL, Headers: headers}, nil
}

// lower is strings.ToLower wrapped so resolver_test.go can reuse it.
func lower(s string) string { return strings.ToLower(s) }
