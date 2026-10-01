package repository

import (
	"account-service/internal/db"
	"gorm.io/gorm"
)

type AuditRepo struct {
	g *gorm.DB
}

func NewAuditRepo(g *gorm.DB) *AuditRepo {
	return &AuditRepo{g: g}
}

func (r *AuditRepo) Insert(l *db.AuditLog) error {
	return r.g.Create(l).Error
}

func (r *AuditRepo) List(filters map[string]interface{}, limit, offset int) ([]db.AuditLog, int64, error) {
	q := r.g.Model(&db.AuditLog{})
	for k, v := range filters {
		q = q.Where(k+" = ?", v)
	}
	var total int64
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	var rows []db.AuditLog
	if err := q.Order("created_at DESC").Limit(limit).Offset(offset).Find(&rows).Error; err != nil {
		return nil, 0, err
	}
	return rows, total, nil
}
