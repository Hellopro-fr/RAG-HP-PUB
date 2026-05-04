package repository

import (
	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/db"
	"gorm.io/gorm"
)

type OAuth2ClientRepo struct {
	g *gorm.DB
}

func NewOAuth2ClientRepo(g *gorm.DB) *OAuth2ClientRepo {
	return &OAuth2ClientRepo{g: g}
}

func (r *OAuth2ClientRepo) Create(c *db.OAuth2Client) error {
	if c.ID == "" {
		c.ID = uuid.New().String()
	}
	return r.g.Create(c).Error
}

func (r *OAuth2ClientRepo) GetByID(id string) (*db.OAuth2Client, error) {
	var c db.OAuth2Client
	if err := r.g.Where("id = ?", id).First(&c).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

func (r *OAuth2ClientRepo) GetByClientID(clientID string) (*db.OAuth2Client, error) {
	var c db.OAuth2Client
	if err := r.g.Where("client_id = ?", clientID).First(&c).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

func (r *OAuth2ClientRepo) GetByName(name string) (*db.OAuth2Client, error) {
	var c db.OAuth2Client
	if err := r.g.Where("name = ? AND is_active = ?", name, true).First(&c).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

func (r *OAuth2ClientRepo) Update(id string, fields map[string]interface{}) error {
	return r.g.Model(&db.OAuth2Client{}).Where("id = ?", id).Updates(fields).Error
}

func (r *OAuth2ClientRepo) Delete(id string) error {
	return r.g.Delete(&db.OAuth2Client{}, "id = ?", id).Error
}

func (r *OAuth2ClientRepo) List(limit, offset int) ([]db.OAuth2Client, int64, error) {
	var clients []db.OAuth2Client
	var total int64
	if err := r.g.Model(&db.OAuth2Client{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	if err := r.g.Order("created_at DESC").Limit(limit).Offset(offset).Find(&clients).Error; err != nil {
		return nil, 0, err
	}
	return clients, total, nil
}
