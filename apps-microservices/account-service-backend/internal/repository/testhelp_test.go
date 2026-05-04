//go:build integration

package repository

import (
	"context"
	"testing"

	"github.com/hellopro/account-service/internal/db"
	"github.com/testcontainers/testcontainers-go/modules/mysql"
	"gorm.io/gorm"
)

func setupTestDB(t *testing.T) *gorm.DB {
	t.Helper()
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
	gormDB, err := db.Connect(dsn)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if err := db.AutoMigrate(gormDB); err != nil {
		t.Fatalf("Migrate: %v", err)
	}
	return gormDB
}
