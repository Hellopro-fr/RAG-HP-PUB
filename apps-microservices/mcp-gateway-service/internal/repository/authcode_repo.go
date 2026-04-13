package repository

import (
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

type AuthCodeRepo struct {
	db *gorm.DB
}

func NewAuthCodeRepo(d *gorm.DB) *AuthCodeRepo {
	return &AuthCodeRepo{db: d}
}

func (r *AuthCodeRepo) Create(code *db.OAuth2AuthorizationCode) error {
	return r.db.Create(code).Error
}

func (r *AuthCodeRepo) FindByHash(hash string) (*db.OAuth2AuthorizationCode, error) {
	var code db.OAuth2AuthorizationCode
	err := r.db.Where("code_hash = ?", hash).First(&code).Error
	if err != nil {
		return nil, err
	}
	return &code, nil
}

func (r *AuthCodeRepo) MarkUsed(hash string) error {
	result := r.db.Model(&db.OAuth2AuthorizationCode{}).
		Where("code_hash = ? AND used_at IS NULL", hash).
		Update("used_at", time.Now())
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

func (r *AuthCodeRepo) PurgeExpired() (int64, error) {
	result := r.db.Where("expires_at < ?", time.Now()).Delete(&db.OAuth2AuthorizationCode{})
	return result.RowsAffected, result.Error
}
