package repository

import (
	"gorm.io/gorm"

	"api-catalog-service/internal/db"
)

type EndpointRepo struct{ g *gorm.DB }

func NewEndpointRepo(g *gorm.DB) *EndpointRepo { return &EndpointRepo{g: g} }

func (r *EndpointRepo) ReplaceForService(serviceID string, rows []db.EndpointRow) error {
	return r.g.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("service_id = ?", serviceID).Delete(&db.EndpointRow{}).Error; err != nil {
			return err
		}
		if len(rows) == 0 {
			return nil
		}
		return tx.CreateInBatches(rows, 200).Error
	})
}

func (r *EndpointRepo) ListForService(serviceID, protocol string) ([]db.EndpointRow, error) {
	q := r.g.Where("service_id = ?", serviceID)
	if protocol != "" {
		q = q.Where("protocol = ?", protocol)
	}
	var items []db.EndpointRow
	if err := q.Order("path ASC").Find(&items).Error; err != nil {
		return nil, err
	}
	return items, nil
}
