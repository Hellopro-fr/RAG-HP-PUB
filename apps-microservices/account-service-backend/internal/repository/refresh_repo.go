package repository

import (
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type RefreshRepo struct {
	g *gorm.DB
}

func NewRefreshRepo(g *gorm.DB) *RefreshRepo {
	return &RefreshRepo{g: g}
}

func (r *RefreshRepo) Create(t *db.OAuth2RefreshToken) error {
	if t.ID == "" {
		t.ID = uuid.New().String()
	}
	return r.g.Create(t).Error
}

func (r *RefreshRepo) FindByHash(hash string) (*db.OAuth2RefreshToken, error) {
	var t db.OAuth2RefreshToken
	if err := r.g.Where("token_hash = ?", hash).First(&t).Error; err != nil {
		return nil, err
	}
	return &t, nil
}

func (r *RefreshRepo) ListBySID(sid string) ([]db.OAuth2RefreshToken, error) {
	var out []db.OAuth2RefreshToken
	err := r.g.Where("sid = ?", sid).Find(&out).Error
	return out, err
}

func (r *RefreshRepo) ListByUser(email string) ([]db.OAuth2RefreshToken, error) {
	var out []db.OAuth2RefreshToken
	err := r.g.Where("user_email = ?", email).Find(&out).Error
	return out, err
}

// Rotate atomically:
//   - looks up the row by oldHash
//   - if it's already revoked: reuse attack, revoke entire sid chain, return error
//   - else mark row revoked, insert new row with same sid
func (r *RefreshRepo) Rotate(oldHash, newHash string) (*db.OAuth2RefreshToken, error) {
	var newRow db.OAuth2RefreshToken
	err := r.g.Transaction(func(tx *gorm.DB) error {
		var existing db.OAuth2RefreshToken
		if err := tx.Where("token_hash = ?", oldHash).First(&existing).Error; err != nil {
			return err
		}
		if existing.Revoked {
			now := time.Now()
			if err := tx.Model(&db.OAuth2RefreshToken{}).
				Where("sid = ?", existing.SID).
				Updates(map[string]interface{}{
					"revoked":        true,
					"revoked_at":     &now,
					"revoked_reason": "reuse_attack",
				}).Error; err != nil {
				return err
			}
			return errors.New("reuse_attack")
		}
		now := time.Now()
		if err := tx.Model(&db.OAuth2RefreshToken{}).
			Where("id = ?", existing.ID).
			Updates(map[string]interface{}{
				"revoked":        true,
				"revoked_at":     &now,
				"revoked_reason": "rotated",
				"last_used_at":   &now,
			}).Error; err != nil {
			return err
		}
		newRow = db.OAuth2RefreshToken{
			ID:          uuid.New().String(),
			TokenHash:   newHash,
			SID:         existing.SID,
			ClientID:    existing.ClientID,
			UserEmail:   existing.UserEmail,
			ExpiresAt:   existing.ExpiresAt,
			RotatedFrom: existing.ID,
		}
		return tx.Create(&newRow).Error
	})
	if err != nil {
		return nil, err
	}
	return &newRow, nil
}

func (r *RefreshRepo) RevokeBySID(sid, reason string) error {
	now := time.Now()
	return r.g.Model(&db.OAuth2RefreshToken{}).
		Where("sid = ? AND revoked = ?", sid, false).
		Updates(map[string]interface{}{
			"revoked":        true,
			"revoked_at":     &now,
			"revoked_reason": reason,
		}).Error
}

func (r *RefreshRepo) RevokeAllForUser(email, reason string) error {
	now := time.Now()
	return r.g.Model(&db.OAuth2RefreshToken{}).
		Where("user_email = ? AND revoked = ?", email, false).
		Updates(map[string]interface{}{
			"revoked":        true,
			"revoked_at":     &now,
			"revoked_reason": reason,
		}).Error
}
