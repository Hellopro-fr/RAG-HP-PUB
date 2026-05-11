package repository

import (
	"errors"
	"time"

	"gorm.io/gorm"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

var ErrNotFound = errors.New("not found")

type ServiceRepo struct{ g *gorm.DB }

func NewServiceRepo(g *gorm.DB) *ServiceRepo { return &ServiceRepo{g: g} }

func (r *ServiceRepo) Create(s *db.ServiceRow) error {
	now := time.Now().UTC()
	if s.CreatedAt.IsZero() {
		s.CreatedAt = now
	}
	s.UpdatedAt = now
	return r.g.Create(s).Error
}

func (r *ServiceRepo) GetByID(id string) (*db.ServiceRow, error) {
	var s db.ServiceRow
	if err := r.g.First(&s, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return &s, nil
}

func (r *ServiceRepo) GetByName(name string) (*db.ServiceRow, error) {
	var s db.ServiceRow
	if err := r.g.First(&s, "name = ?", name).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return &s, nil
}

func (r *ServiceRepo) List(limit, offset int, filter string) ([]db.ServiceRow, int64, error) {
	if limit <= 0 {
		limit = 100
	}
	q := r.g.Model(&db.ServiceRow{})
	if filter != "" {
		q = q.Where("name LIKE ?", "%"+filter+"%")
	}
	var total int64
	if err := q.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	var items []db.ServiceRow
	if err := q.Order("name ASC").Limit(limit).Offset(offset).Find(&items).Error; err != nil {
		return nil, 0, err
	}
	return items, total, nil
}

func (r *ServiceRepo) Update(id string, fields map[string]any) error {
	fields["updated_at"] = time.Now().UTC()
	res := r.g.Model(&db.ServiceRow{}).Where("id = ?", id).Updates(fields)
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *ServiceRepo) Delete(id string) error {
	res := r.g.Delete(&db.ServiceRow{}, "id = ?", id)
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *ServiceRepo) ListAll() ([]db.ServiceRow, error) {
	var items []db.ServiceRow
	if err := r.g.Find(&items).Error; err != nil {
		return nil, err
	}
	return items, nil
}
