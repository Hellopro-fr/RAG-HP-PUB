package db

import (
	"fmt"
	"log"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// Connect opens a GORM connection to MySQL and auto-migrates all models.
func Connect(dsn string) (*gorm.DB, error) {
	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Warn),
	})
	if err != nil {
		return nil, fmt.Errorf("open mysql: %w", err)
	}

	sqlDB, err := db.DB()
	if err != nil {
		return nil, fmt.Errorf("get sql.DB: %w", err)
	}
	sqlDB.SetMaxOpenConns(25)
	sqlDB.SetMaxIdleConns(5)

	log.Println("[db] connected to MySQL")

	if err := db.AutoMigrate(
		&MCPServer{},
		&ServerTool{},
		&ServerResource{},
		&ServerPrompt{},
		&PromptArgument{},
		&ServerTag{},
	); err != nil {
		return nil, fmt.Errorf("auto-migrate: %w", err)
	}

	log.Println("[db] migrations applied")
	return db, nil
}
