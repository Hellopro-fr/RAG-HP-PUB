package repository

import (
	"mcp-gateway/internal/db"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

type ConsentRepo struct {
	db *gorm.DB
}

func NewConsentRepo(d *gorm.DB) *ConsentRepo {
	return &ConsentRepo{db: d}
}

func (r *ConsentRepo) FindByClientAndUser(clientID, userEmail string) (*db.OAuth2Consent, error) {
	var consent db.OAuth2Consent
	err := r.db.Where("client_id = ? AND user_email = ?", clientID, userEmail).First(&consent).Error
	if err != nil {
		return nil, err
	}
	return &consent, nil
}

func (r *ConsentRepo) Upsert(consent *db.OAuth2Consent) error {
	return r.db.Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "client_id"}, {Name: "user_email"}},
		DoUpdates: clause.AssignmentColumns([]string{"scope", "updated_at"}),
	}).Create(consent).Error
}
