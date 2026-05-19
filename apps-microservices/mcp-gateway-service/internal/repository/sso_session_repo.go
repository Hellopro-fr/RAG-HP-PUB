package repository

import (
	"time"

	"mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// SSOSessionRepo manages sso_sessions rows backing admin-UI browser sessions
// for the account-service OAuth2 client flow.
type SSOSessionRepo struct {
	db *gorm.DB
}

func NewSSOSessionRepo(d *gorm.DB) *SSOSessionRepo {
	return &SSOSessionRepo{db: d}
}

func (r *SSOSessionRepo) Create(s *db.SSOSession) error {
	return r.db.Create(s).Error
}

func (r *SSOSessionRepo) FindByID(id string) (*db.SSOSession, error) {
	var s db.SSOSession
	if err := r.db.Where("id = ?", id).First(&s).Error; err != nil {
		return nil, err
	}
	return &s, nil
}

func (r *SSOSessionRepo) UpdateTokens(id string, access, refresh []byte, accessExp, refreshExp time.Time) error {
	return r.db.Model(&db.SSOSession{}).
		Where("id = ?", id).
		Updates(map[string]interface{}{
			"access_token":  access,
			"refresh_token": refresh,
			"access_exp":    accessExp,
			"refresh_exp":   refreshExp,
			"last_seen_at":  time.Now(),
		}).Error
}

func (r *SSOSessionRepo) Touch(id string) error {
	return r.db.Model(&db.SSOSession{}).
		Where("id = ?", id).
		Update("last_seen_at", time.Now()).Error
}

func (r *SSOSessionRepo) Delete(id string) error {
	return r.db.Where("id = ?", id).Delete(&db.SSOSession{}).Error
}

// DeleteBySub removes every session for a user (sub = account-service stable id).
// Used by the account-service-initiated logout webhook receiver.
func (r *SSOSessionRepo) DeleteBySub(sub string) (int64, error) {
	res := r.db.Where("sub = ?", sub).Delete(&db.SSOSession{})
	return res.RowsAffected, res.Error
}

// ReapExpired removes sessions whose refresh token already expired beyond the
// grace window. Called periodically from a background goroutine.
func (r *SSOSessionRepo) ReapExpired(grace time.Duration) (int64, error) {
	cutoff := time.Now().Add(-grace)
	res := r.db.Where("refresh_exp < ?", cutoff).Delete(&db.SSOSession{})
	return res.RowsAffected, res.Error
}
