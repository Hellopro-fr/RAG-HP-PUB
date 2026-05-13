package db

import (
	"fmt"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

func Open(host, port, user, pass, name string) (*gorm.DB, error) {
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true&charset=utf8mb4", user, pass, host, port, name)
	g, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, fmt.Errorf("open mysql: %w", err)
	}
	return g, nil
}

func AutoMigrate(g *gorm.DB) error {
	return g.AutoMigrate(&ServiceRow{}, &EndpointRow{})
}
