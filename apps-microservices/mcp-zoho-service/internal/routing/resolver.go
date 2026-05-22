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
	ErrNoZohoConfigured      = errors.New("no_zoho_configured")
	ErrNoAdminZohoConfigured = errors.New("no_admin_zoho_configured")
	ErrMisconfigured         = errors.New("misconfigured")
	ErrInvalidIdentity       = errors.New("invalid_identity")
)

// QueryRunner is the narrow contract resolver needs from the DB layer.
type QueryRunner interface {
	FindAdminZohoImport(ctx context.Context) (*db.ImportRow, error)
	IsAdminGranted(ctx context.Context, stubServerID, email string) (bool, error)
	FindUserZohoImport(ctx context.Context, email, login string) (*db.ImportRow, error)
}

// Decryptor unwraps an encrypted blob (zoho_imports.auth_headers).
type Decryptor interface {
	Decrypt([]byte) ([]byte, error)
}

// Resolver maps a caller's identity to an upstream Zoho URL.
type Resolver struct {
	q            QueryRunner
	dec          Decryptor
	cache        *cache
	stubServerID string
}

// NewResolver wires the dependencies.
func NewResolver(q QueryRunner, dec Decryptor, ttl time.Duration, stubServerID string) *Resolver {
	return &Resolver{q: q, dec: dec, cache: newCache(ttl), stubServerID: stubServerID}
}

// Resolve returns the upstream URL and decrypted headers for the caller, or
// one of the sentinel errors above. The cache is consulted first.
//
// When email and login are both empty, the caller has no end-user identity
// — this is the gateway's discovery / health-probe path (POST /mcp with
// initialize or tools/list at boot, no user context). In that case we route
// to the admin Zoho row so the gateway sees a real backend instead of a
// 400. Per-user routing still applies whenever an end-user email is
// supplied.
func (r *Resolver) Resolve(ctx context.Context, email, login string) (*Resolution, error) {
	// Branch 1: discovery / health-probe path (no end-user identity).
	if email == "" && login == "" {
		log.Printf("[resolver] branch=discovery email='' login='' — routing to admin row")
		adminRow, aerr := r.q.FindAdminZohoImport(ctx)
		if aerr != nil {
			if errors.Is(aerr, sql.ErrNoRows) {
				log.Printf("[resolver] branch=discovery result=no_admin_zoho_configured (admin row missing)")
				return nil, ErrNoAdminZohoConfigured
			}
			log.Printf("[resolver] branch=discovery result=error finding admin: %v", aerr)
			return nil, fmt.Errorf("find admin row (no end-user): %w", aerr)
		}
		log.Printf("[resolver] branch=discovery result=admin row_id=%s url=%s", adminRow.ID, adminRow.URL)
		return r.buildResolution(adminRow)
	}

	key := lower(email)
	if v, ok := r.cache.get(key); ok {
		log.Printf("[resolver] branch=cache email=%s url=%s", email, v.UpstreamURL)
		return v, nil
	}

	// Branch 2: admin gate. server_authorizations row on the stub server
	// grants this email full admin access to the Zoho backend.
	granted, err := r.q.IsAdminGranted(ctx, r.stubServerID, email)
	if err != nil {
		log.Printf("[resolver] branch=admin_gate result=error email=%s err=%v", email, err)
		return nil, fmt.Errorf("server_authorizations lookup: %w", err)
	}
	if granted {
		log.Printf("[resolver] branch=admin_grant email=%s stub_id=%s — routing to admin row", email, r.stubServerID)
		adminRow, aerr := r.q.FindAdminZohoImport(ctx)
		if aerr != nil {
			if errors.Is(aerr, sql.ErrNoRows) {
				log.Printf("[resolver] branch=admin_grant email=%s result=no_admin_zoho_configured (admin row missing)", email)
				return nil, ErrNoAdminZohoConfigured
			}
			log.Printf("[resolver] branch=admin_grant email=%s result=error finding admin: %v", email, aerr)
			return nil, fmt.Errorf("find admin row: %w", aerr)
		}
		res, berr := r.buildResolution(adminRow)
		if berr != nil {
			log.Printf("[resolver] branch=admin_grant email=%s result=error building resolution: %v", email, berr)
			return nil, berr
		}
		log.Printf("[resolver] branch=admin_grant email=%s result=admin row_id=%s url=%s", email, adminRow.ID, adminRow.URL)
		r.cache.set(key, res)
		return res, nil
	}

	// Branch 3: per-user import lookup. Matches zoho_imports.created_by
	// against email (exact, case-insensitive) or login portion.
	userRow, err := r.q.FindUserZohoImport(ctx, email, login)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			log.Printf("[resolver] branch=user_lookup email=%s login=%s result=no_zoho_configured (no matching import)", email, login)
			return nil, ErrNoZohoConfigured
		}
		log.Printf("[resolver] branch=user_lookup email=%s login=%s result=error: %v", email, login, err)
		return nil, fmt.Errorf("find user row: %w", err)
	}

	// Defensive Go-side match (the SQL already filtered).
	if !matchesUserEmail(userRow.CreatedBy, email, login) {
		log.Printf("[resolver] branch=user_lookup email=%s login=%s result=no_zoho_configured (SQL matched created_by=%q but Go-side matchesUserEmail rejected — possible SQL/algorithm drift)", email, login, userRow.CreatedBy)
		return nil, ErrNoZohoConfigured
	}

	log.Printf("[resolver] branch=user_lookup email=%s login=%s result=hit row_id=%s created_by=%s url=%s", email, login, userRow.ID, userRow.CreatedBy, userRow.URL)

	res, err := r.buildResolution(userRow)
	if err != nil {
		log.Printf("[resolver] branch=user_lookup email=%s result=error building resolution: %v", email, err)
		return nil, err
	}
	r.cache.set(key, res)
	return res, nil
}

func (r *Resolver) buildResolution(row *db.ImportRow) (*Resolution, error) {
	headers := map[string]string{}
	if len(row.AuthHeaders) > 0 {
		pt, err := r.dec.Decrypt(row.AuthHeaders)
		if err != nil {
			log.Printf("[resolver] buildResolution row_id=%s decrypt FAILED: %v (rotating ENCRYPTION_KEY would invalidate stored blobs)", row.ID, err)
			return nil, fmt.Errorf("decrypt auth_headers for row %s: %w", row.ID, err)
		}
		if err := json.Unmarshal(pt, &headers); err != nil {
			log.Printf("[resolver] buildResolution row_id=%s json unmarshal FAILED: %v (stored blob is not a JSON map)", row.ID, err)
			return nil, fmt.Errorf("decode auth_headers for row %s: %w", row.ID, err)
		}
		keys := make([]string, 0, len(headers))
		for k := range headers {
			keys = append(keys, k)
		}
		log.Printf("[resolver] buildResolution row_id=%s url=%s header_keys=%v", row.ID, row.URL, keys)
	} else {
		log.Printf("[resolver] buildResolution row_id=%s url=%s header_keys=[] (no auth_headers stored)", row.ID, row.URL)
	}
	return &Resolution{UpstreamURL: row.URL, Headers: headers}, nil
}

// lower is strings.ToLower wrapped so resolver_test.go can reuse it.
func lower(s string) string { return strings.ToLower(s) }
