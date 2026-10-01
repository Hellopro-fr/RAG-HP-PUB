package repository

import (
	"time"

	"mcp-gateway/internal/db"
	"gorm.io/gorm"
)

type RefreshRepo struct {
	db *gorm.DB
}

func NewRefreshRepo(d *gorm.DB) *RefreshRepo {
	return &RefreshRepo{db: d}
}

func (r *RefreshRepo) Create(token *db.OAuth2RefreshToken) error {
	return r.db.Create(token).Error
}

func (r *RefreshRepo) FindByHash(hash string) (*db.OAuth2RefreshToken, error) {
	var token db.OAuth2RefreshToken
	err := r.db.Where("token_hash = ?", hash).First(&token).Error
	if err != nil {
		return nil, err
	}
	return &token, nil
}

func (r *RefreshRepo) Revoke(hash string) error {
	return r.db.Model(&db.OAuth2RefreshToken{}).
		Where("token_hash = ?", hash).
		Update("revoked_at", time.Now()).Error
}

func (r *RefreshRepo) RevokeAllForClient(clientID string) error {
	return r.db.Model(&db.OAuth2RefreshToken{}).
		Where("client_id = ? AND revoked_at IS NULL", clientID).
		Update("revoked_at", time.Now()).Error
}

func (r *RefreshRepo) PurgeExpired(olderThan time.Duration) (int64, error) {
	cutoff := time.Now().Add(-olderThan)
	result := r.db.Where("expires_at < ? OR (revoked_at IS NOT NULL AND revoked_at < ?)", cutoff, cutoff).
		Delete(&db.OAuth2RefreshToken{})
	return result.RowsAffected, result.Error
}
