package repository

import (
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// InstallGuideRepo provides CRUD operations on install executors and configs.
type InstallGuideRepo struct {
	db *gorm.DB
}

// NewInstallGuideRepo creates a new InstallGuideRepo.
func NewInstallGuideRepo(database *gorm.DB) *InstallGuideRepo {
	return &InstallGuideRepo{db: database}
}

// ── Executors ──────────────────────────────────────────────────────

// ListExecutors returns all executors ordered by display_order.
// If activeOnly is true, only active executors are returned.
func (r *InstallGuideRepo) ListExecutors(activeOnly bool) ([]db.InstallExecutor, error) {
	q := r.db.Order("display_order ASC, id ASC")
	if activeOnly {
		q = q.Where("is_active = ?", true)
	}
	var executors []db.InstallExecutor
	if err := q.Find(&executors).Error; err != nil {
		return nil, err
	}
	return executors, nil
}

// GetExecutor returns an executor by ID.
func (r *InstallGuideRepo) GetExecutor(id uint64) (*db.InstallExecutor, error) {
	var e db.InstallExecutor
	if err := r.db.First(&e, id).Error; err != nil {
		return nil, err
	}
	return &e, nil
}

// GetExecutorBySlug returns an executor by slug.
func (r *InstallGuideRepo) GetExecutorBySlug(slug string) (*db.InstallExecutor, error) {
	var e db.InstallExecutor
	if err := r.db.Where("slug = ?", slug).First(&e).Error; err != nil {
		return nil, err
	}
	return &e, nil
}

// CreateExecutor inserts a new executor.
func (r *InstallGuideRepo) CreateExecutor(e *db.InstallExecutor) error {
	return r.db.Create(e).Error
}

// UpdateExecutor updates an executor by ID.
func (r *InstallGuideRepo) UpdateExecutor(id uint64, updates map[string]interface{}) error {
	return r.db.Model(&db.InstallExecutor{}).Where("id = ?", id).Updates(updates).Error
}

// DeleteExecutor removes an executor by ID.
func (r *InstallGuideRepo) DeleteExecutor(id uint64) error {
	return r.db.Delete(&db.InstallExecutor{}, id).Error
}

// ── Configs ────────────────────────────────────────────────────────

// ListConfigs returns all configs ordered by display_order.
// If activeOnly is true, only active configs are returned.
func (r *InstallGuideRepo) ListConfigs(activeOnly bool) ([]db.InstallConfig, error) {
	q := r.db.Order("display_order ASC, id ASC")
	if activeOnly {
		q = q.Where("is_active = ?", true)
	}
	var configs []db.InstallConfig
	if err := q.Find(&configs).Error; err != nil {
		return nil, err
	}
	return configs, nil
}

// GetConfig returns a config by ID.
func (r *InstallGuideRepo) GetConfig(id uint64) (*db.InstallConfig, error) {
	var c db.InstallConfig
	if err := r.db.First(&c, id).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

// GetConfigBySlug returns a config by slug.
func (r *InstallGuideRepo) GetConfigBySlug(slug string) (*db.InstallConfig, error) {
	var c db.InstallConfig
	if err := r.db.Where("slug = ?", slug).First(&c).Error; err != nil {
		return nil, err
	}
	return &c, nil
}

// CreateConfig inserts a new config.
func (r *InstallGuideRepo) CreateConfig(c *db.InstallConfig) error {
	return r.db.Create(c).Error
}

// UpdateConfig updates a config by ID.
func (r *InstallGuideRepo) UpdateConfig(id uint64, updates map[string]interface{}) error {
	return r.db.Model(&db.InstallConfig{}).Where("id = ?", id).Updates(updates).Error
}

// DeleteConfig removes a config by ID.
func (r *InstallGuideRepo) DeleteConfig(id uint64) error {
	return r.db.Delete(&db.InstallConfig{}, id).Error
}
