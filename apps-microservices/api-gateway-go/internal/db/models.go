package db

import "time"

// int64 with size:32 maps to int (signed 32-bit) in MySQL, matching the Python
// Tortoise ORM schema which created these tables with int NOT NULL AUTO_INCREMENT.
// GORM's MySQL driver picks the SQL type by field.Size: ≤32 → int, >32 → bigint.
// Using int64 in Go avoids overflow issues while forcing int at the DB level.

type InfoRefreshToken struct {
	ID           int64     `gorm:"column:id;size:32;primaryKey;autoIncrement"`
	NomService   string    `gorm:"column:nom_service;size:128;index"`
	Token        string    `gorm:"column:token;size:768;index"`
	DateCreation time.Time `gorm:"column:date_creation;autoCreateTime"`
	IPCreation   string    `gorm:"column:ip_creation;size:64;default:system"`
	EstActif     bool      `gorm:"column:est_actif;default:true;index"`
}

func (InfoRefreshToken) TableName() string { return "info_refresh_token" }

type InfoAccessToken struct {
	ID             int64            `gorm:"column:id;size:32;primaryKey;autoIncrement"`
	IDRefreshToken int64            `gorm:"column:id_refresh_token_id;size:32;index"`
	RefreshToken   InfoRefreshToken `gorm:"foreignKey:IDRefreshToken;references:ID;constraint:OnDelete:CASCADE"`
	Token          string           `gorm:"column:token;size:768;index"`
	DateCreation   time.Time        `gorm:"column:date_creation;autoCreateTime"`
	DateExpiration time.Time        `gorm:"column:date_expiration"`
	EstActif       bool             `gorm:"column:est_actif;default:true;index"`
}

func (InfoAccessToken) TableName() string { return "info_access_token" }

type ApiCallHistory struct {
	ID             int64     `gorm:"column:id;size:32;primaryKey;autoIncrement"`
	ServiceName    string    `gorm:"column:service_name;size:128;index"`
	Method         string    `gorm:"column:method;size:10"`
	Path           string    `gorm:"column:path;type:text"`
	StatusCode     int       `gorm:"column:status_code"`
	ClientIP       string    `gorm:"column:client_ip;size:64"`
	RequestHeaders *string   `gorm:"column:request_headers;type:text"`
	CalledAt       time.Time `gorm:"column:called_at;autoCreateTime;index"`
	DurationMs     *int      `gorm:"column:duration_ms"`
}

func (ApiCallHistory) TableName() string { return "api_call_history" }
