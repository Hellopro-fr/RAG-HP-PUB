package db

import (
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

func openTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := AutoMigrate(g); err != nil {
		t.Fatal(err)
	}
	return g
}

func TestAutoMigrate_CreatesTables(t *testing.T) {
	g := openTestDB(t)
	if !g.Migrator().HasTable(&ServiceRow{}) {
		t.Fatal("catalog_services table missing")
	}
	if !g.Migrator().HasTable(&EndpointRow{}) {
		t.Fatal("catalog_endpoints table missing")
	}
}
