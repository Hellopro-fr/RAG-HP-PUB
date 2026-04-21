package repository

import (
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// TemplateRepo provides read-only access to the seed-data templates catalog.
type TemplateRepo struct {
	db *gorm.DB
}

// NewTemplateRepo creates a new repository for read access to the templates catalog.
func NewTemplateRepo(database *gorm.DB) *TemplateRepo {
	return &TemplateRepo{db: database}
}

// ListActive returns templates where is_active = true, ordered by name.
func (r *TemplateRepo) ListActive() ([]db.Template, error) {
	var out []db.Template
	err := r.db.Where("is_active = ?", true).Order("name ASC").Find(&out).Error
	return out, err
}

// GetBySlug returns a single active template by slug. Returns gorm.ErrRecordNotFound
// when the slug does not exist or the template is inactive.
func (r *TemplateRepo) GetBySlug(slug string) (*db.Template, error) {
	var t db.Template
	if err := r.db.First(&t, "slug = ? AND is_active = ?", slug, true).Error; err != nil {
		return nil, err
	}
	return &t, nil
}
