package db

import "time"

type User struct {
	ID          string `gorm:"type:char(36);primaryKey"`
	Email       string `gorm:"size:255;uniqueIndex;not null"`
	DisplayName string `gorm:"size:255"`
	IsAdmin     bool   `gorm:"not null;default:false"`
	IsAllowed   bool   `gorm:"not null;default:true"`
	LastLoginAt *time.Time
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

type OAuth2Client struct {
	ID                string `gorm:"type:char(36);primaryKey"`
	ClientID          string `gorm:"size:64;uniqueIndex;not null"`
	ClientSecretEnc   []byte `gorm:"type:blob;not null"`
	Name              string `gorm:"size:255;not null"`
	Description       string `gorm:"type:text"`
	LogoURL           string `gorm:"size:512"`
	BrandColor        string `gorm:"size:16"`
	RedirectURIs      *string `gorm:"type:json"`
	AllowedRoles      *string `gorm:"type:json"`
	LogoutWebhookURL  string `gorm:"size:512"`
	TokenTTLSeconds   int     `gorm:"not null;default:60"`
	RefreshTTLSeconds int     `gorm:"not null;default:2592000"`
	ClaimMappings     *string `gorm:"type:json"`
	Scope             string  `gorm:"size:512"`
	IsActive          bool    `gorm:"not null;default:true"`
	CreatedBy         string  `gorm:"size:255"`
	CreatedAt         time.Time
	UpdatedAt         time.Time
}

type OAuth2AuthorizationCode struct {
	CodeHash      string    `gorm:"type:char(64);primaryKey"`
	ClientID      string    `gorm:"size:64;not null;index:idx_authcode_purge,priority:1"`
	UserEmail     string    `gorm:"size:255;not null"`
	RedirectURI   string    `gorm:"size:512;not null"`
	CodeChallenge string    `gorm:"size:128;not null"`
	Scope         string    `gorm:"size:512"`
	Used          bool      `gorm:"not null;default:false"`
	ExpiresAt     time.Time `gorm:"not null;index:idx_authcode_purge,priority:2"`
	CreatedAt     time.Time
}

type OAuth2RefreshToken struct {
	ID            string    `gorm:"type:char(36);primaryKey"`
	TokenHash     string    `gorm:"type:char(64);uniqueIndex;not null"`
	SID           string    `gorm:"type:char(36);not null;index"`
	ClientID      string    `gorm:"size:64;not null"`
	UserEmail     string    `gorm:"size:255;not null;index:idx_refresh_user,priority:1"`
	ExpiresAt     time.Time `gorm:"not null"`
	Revoked       bool      `gorm:"not null;default:false;index:idx_refresh_user,priority:2"`
	RevokedAt     *time.Time
	RevokedReason string `gorm:"size:64"`
	RotatedFrom   string `gorm:"type:char(36);index"`
	CreatedAt     time.Time
	LastUsedAt    *time.Time
}

type LogoutEvent struct {
	ID            string    `gorm:"type:char(36);primaryKey"`
	ClientID      string    `gorm:"size:64;not null"`
	UserEmail     string    `gorm:"size:255;not null"`
	SID           string    `gorm:"type:char(36);not null"`
	WebhookURL    string    `gorm:"size:512;not null"`
	Status        string    `gorm:"size:16;not null;default:'pending';index:idx_logout_pickup,priority:1"`
	Attempts      int       `gorm:"not null;default:0"`
	LastError     string    `gorm:"type:text"`
	NextAttemptAt time.Time `gorm:"index:idx_logout_pickup,priority:2"`
	CreatedAt     time.Time
	UpdatedAt     time.Time
}

type AuditLog struct {
	ID          int64  `gorm:"primaryKey;autoIncrement"`
	Event       string `gorm:"size:32;not null;index:idx_audit_event,priority:1"`
	ActorEmail  string `gorm:"size:255;index:idx_audit_actor,priority:1"`
	TargetEmail string `gorm:"size:255"`
	ClientID    string `gorm:"size:64"`
	IPAddr      string `gorm:"size:64"`
	UserAgent   string `gorm:"size:512"`
	Metadata    *string `gorm:"type:json"`
	CreatedAt   time.Time `gorm:"index:idx_audit_event,priority:2;index:idx_audit_actor,priority:2"`
}
