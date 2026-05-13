package db

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"

	_ "github.com/go-sql-driver/mysql"
)

// TestQueries_Smoke is an integration smoke test against a live MySQL
// instance carrying the gateway schema. Skipped when MYSQL_TEST_DSN is
// unset so `go test` stays green on dev laptops without MySQL.
func TestQueries_Smoke(t *testing.T) {
	dsn := os.Getenv("MYSQL_TEST_DSN")
	if dsn == "" {
		t.Skip("MYSQL_TEST_DSN unset; skipping integration smoke")
	}
	conn, err := Open(dsn)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer conn.Close()

	ctx := context.Background()
	q := NewQueries(conn)

	if _, err := q.FindAdminZohoImport(ctx); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("FindAdminZohoImport: %v", err)
	}
	if _, err := q.FindUserZohoImport(ctx, "alice@hp.fr", "alice"); err != nil && !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("FindUserZohoImport: %v", err)
	}
	if _, err := q.IsAdminGranted(ctx, "any-stub-id", "alice@hp.fr"); err != nil {
		t.Fatalf("IsAdminGranted: %v", err)
	}
}
