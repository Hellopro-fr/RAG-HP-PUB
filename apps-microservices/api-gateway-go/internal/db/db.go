package db

import (
	"context"
	"fmt"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// BuildDSN constructs a MySQL DSN string from individual components.
func BuildDSN(user, pass, host, port, name string) string {
	return fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=true&loc=UTC",
		user, pass, host, port, name)
}

// Open initializes a GORM MySQL connection and verifies connectivity.
func Open(ctx context.Context, dsn string) (*gorm.DB, error) {
	gdb, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Warn),
	})
	if err != nil {
		return nil, fmt.Errorf("gorm.Open: %w", err)
	}
	sqlDB, err := gdb.DB()
	if err != nil {
		return nil, fmt.Errorf("gdb.DB: %w", err)
	}
	if err := sqlDB.PingContext(ctx); err != nil {
		return nil, fmt.Errorf("ping: %w", err)
	}
	return gdb, nil
}

// AutoMigrate runs GORM AutoMigrate for all gateway models.
func AutoMigrate(gdb *gorm.DB) error {
	return gdb.AutoMigrate(&InfoRefreshToken{}, &InfoAccessToken{}, &ApiCallHistory{})
}
