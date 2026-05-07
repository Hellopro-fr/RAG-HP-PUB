package db

import "time"

type InfoRefreshToken struct {
	ID           uint      `gorm:"column:id;primaryKey;autoIncrement"`
	NomService   string    `gorm:"column:nom_service;size:128;index"`
	Token        string    `gorm:"column:token;size:768;index"`
	DateCreation time.Time `gorm:"column:date_creation;autoCreateTime"`
	IPCreation   string    `gorm:"column:ip_creation;size:64;default:system"`
	EstActif     bool      `gorm:"column:est_actif;default:true;index"`
}

func (InfoRefreshToken) TableName() string { return "info_refresh_token" }

type InfoAccessToken struct {
	ID             uint             `gorm:"column:id;primaryKey;autoIncrement"`
	IDRefreshToken uint             `gorm:"column:id_refresh_token_id;index"`
	RefreshToken   InfoRefreshToken `gorm:"foreignKey:IDRefreshToken;references:ID;constraint:OnDelete:CASCADE"`
	Token          string           `gorm:"column:token;size:768;index"`
	DateCreation   time.Time        `gorm:"column:date_creation;autoCreateTime"`
	DateExpiration time.Time        `gorm:"column:date_expiration"`
	EstActif       bool             `gorm:"column:est_actif;default:true;index"`
}

func (InfoAccessToken) TableName() string { return "info_access_token" }

type ApiCallHistory struct {
	ID             uint      `gorm:"column:id;primaryKey;autoIncrement"`
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
