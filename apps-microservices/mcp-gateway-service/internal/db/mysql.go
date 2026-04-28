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
		&ScopeToken{},
		&ScopeTokenServer{},
		&ScopeTokenTool{},
		&OAuth2Client{},
		&OAuth2ClientServer{},
		&OAuth2ClientTool{},
		&OAuth2AuthorizationCode{},
		&OAuth2RefreshToken{},
		&OAuth2Consent{},
		&GatewayUser{},
		&AuditLog{},
		&InstallExecutor{},
		&InstallConfig{},
		&UserGoogleToken{},
		&Template{},
		&TemplateInstance{},
		&LLMInstruction{},
		&LLMInstructionRow{},
		&LLMInstructionRowServer{},
		&ScopeTokenInstruction{},
		&OAuth2ClientInstruction{},
		&BDDUsedTable{},
		&BDDUsedField{},
		&BDDMeta{},
		&ScopeTokenBDDTable{},
		&OAuth2ClientBDDTable{},
	); err != nil {
		return nil, fmt.Errorf("auto-migrate: %w", err)
	}

	log.Println("[db] migrations applied")

	// One-time migration: merge mcp_headers into auth_headers.
	// For servers that have mcp_headers but no auth_headers, copy the value over.
	// The old mcp_headers column is left in place (GORM AutoMigrate doesn't drop columns).
	if db.Migrator().HasColumn(&MCPServer{}, "mcp_headers") {
		result := db.Exec(`
			UPDATE mcp_servers
			SET auth_headers = mcp_headers, mcp_headers = NULL
			WHERE mcp_headers IS NOT NULL
			  AND mcp_headers != 'null'
			  AND mcp_headers != '{}'
			  AND (auth_headers IS NULL OR auth_headers = '' OR auth_headers = X'')
		`)
		if result.Error != nil {
			log.Printf("[db] warning: mcp_headers migration failed: %v", result.Error)
		} else if result.RowsAffected > 0 {
			log.Printf("[db] migrated mcp_headers → auth_headers for %d servers", result.RowsAffected)
		}
	}

	return db, nil
}
