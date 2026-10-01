package db

import "time"

// ServiceRow maps to the catalog_services MySQL table.
// GORM type tags (enum, json) are MySQL-specific DDL hints; the SQL schema in
// init-db/01_schema.sql is the authoritative DDL for production. SQLite (used
// in tests) ignores unsupported types so we use size constraints here instead
// of enum/json literals, which would cause syntax errors in SQLite AutoMigrate.
type ServiceRow struct {
	ID              string `gorm:"type:char(36);primaryKey"`
	Name            string `gorm:"size:128;uniqueIndex;not null"`
	BaseURL         string `gorm:"size:512;not null"`
	Protocols       string `gorm:"size:1024;not null"`
	Source          string `gorm:"size:16;not null"`
	Status          string `gorm:"size:16;not null;default:'active'"`
	Description     string `gorm:"type:text"`
	Owner           string `gorm:"size:128"`
	Tags            string `gorm:"size:1024"`
	APIInfoURL      string `gorm:"size:512;column:api_info_url"`
	GRPCAddress     string `gorm:"size:512;column:grpc_address"`
	LastScannedAt   *time.Time
	LastScanOK      *bool  `gorm:"column:last_scan_ok"`
	LastScanError   string `gorm:"type:text;column:last_scan_error"`
	CreatedBy       string `gorm:"size:255"`
	AuthPolicy      int    `gorm:"column:auth_policy;not null;default:1"`
	PublicPaths     string `gorm:"size:2048;column:public_paths"`
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

func (ServiceRow) TableName() string { return "catalog_services" }

type EndpointRow struct {
	ID          string `gorm:"type:char(36);primaryKey"`
	ServiceID   string `gorm:"type:char(36);not null;index"`
	Protocol    string `gorm:"size:8;not null"`
	Method      string `gorm:"size:16"`
	Path        string `gorm:"size:512;not null"`
	Summary     string `gorm:"size:512"`
	OperationID string `gorm:"size:255;column:operation_id"`
	Tags        string `gorm:"size:1024"`
	Deprecated  bool   `gorm:"not null;default:false"`
	AuthPolicy  *int   `gorm:"column:auth_policy"`
}

func (EndpointRow) TableName() string { return "catalog_endpoints" }
