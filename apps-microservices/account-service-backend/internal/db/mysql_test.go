//go:build integration

package db

import (
	"context"
	"testing"

	"github.com/testcontainers/testcontainers-go/modules/mysql"
)

func TestConnectAndMigrate(t *testing.T) {
	ctx := context.Background()
	container, err := mysql.Run(ctx,
		"mysql:8.0",
		mysql.WithDatabase("account_db"),
		mysql.WithUsername("acct"),
		mysql.WithPassword("acct"),
	)
	if err != nil {
		t.Fatalf("container: %v", err)
	}
	t.Cleanup(func() { _ = container.Terminate(ctx) })

	dsn, err := container.ConnectionString(ctx, "parseTime=true")
	if err != nil {
		t.Fatalf("dsn: %v", err)
	}
	gormDB, err := Connect(dsn)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if err := AutoMigrate(gormDB); err != nil {
		t.Fatalf("AutoMigrate: %v", err)
	}
	for _, name := range []string{"users", "oauth2_clients", "oauth2_authorization_codes", "oauth2_refresh_tokens", "logout_events", "audit_logs"} {
		if !gormDB.Migrator().HasTable(name) {
			t.Errorf("table %s missing after migrate", name)
		}
	}
}
