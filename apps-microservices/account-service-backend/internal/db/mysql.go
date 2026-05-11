package db

import (
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func Connect(dsn string) (*gorm.DB, error) {
	gormDB, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, err
	}
	sqlDB, err := gormDB.DB()
	if err != nil {
		return nil, err
	}
	sqlDB.SetMaxOpenConns(25)
	sqlDB.SetMaxIdleConns(5)
	sqlDB.SetConnMaxLifetime(time.Hour)
	return gormDB, nil
}

func AutoMigrate(g *gorm.DB) error {
	return g.AutoMigrate(
		&User{},
		&OAuth2Client{},
		&OAuth2AuthorizationCode{},
		&OAuth2RefreshToken{},
		&LogoutEvent{},
		&AuditLog{},
	)
}
