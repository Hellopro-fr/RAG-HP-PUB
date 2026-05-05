package repository

import (
	"errors"
	"time"

	"account-service/internal/db"
	"gorm.io/gorm"
)

type AuthCodeRepo struct {
	g *gorm.DB
}

func NewAuthCodeRepo(g *gorm.DB) *AuthCodeRepo {
	return &AuthCodeRepo{g: g}
}

func (r *AuthCodeRepo) Create(c *db.OAuth2AuthorizationCode) error {
	return r.g.Create(c).Error
}

// ConsumeUnused finds an unused, non-expired code by hash and marks it used in
// the same transaction. Returns the row content as it was before the flag flip.
func (r *AuthCodeRepo) ConsumeUnused(codeHash string) (*db.OAuth2AuthorizationCode, error) {
	var out db.OAuth2AuthorizationCode
	err := r.g.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("code_hash = ? AND used = ? AND expires_at > ?", codeHash, false, time.Now()).
			First(&out).Error; err != nil {
			return err
		}
		return tx.Model(&db.OAuth2AuthorizationCode{}).
			Where("code_hash = ? AND used = ?", codeHash, false).
			Update("used", true).Error
	})
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("invalid_grant")
		}
		return nil, err
	}
	return &out, nil
}

func (r *AuthCodeRepo) PurgeExpired() (int64, error) {
	res := r.g.Where("expires_at < ?", time.Now()).Delete(&db.OAuth2AuthorizationCode{})
	return res.RowsAffected, res.Error
}
