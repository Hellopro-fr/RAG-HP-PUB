package repository

import (
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"

	"mcp-gateway/internal/db"
)

// ErrAdminCreatedByMustBeEmpty is returned by UpdateOrCreateAdmin when the
// caller supplies a non-empty CreatedBy on the admin row.
var ErrAdminCreatedByMustBeEmpty = errors.New("admin zoho import must have empty created_by")

// ZohoImportRepo provides CRUD for the zoho_imports table.
type ZohoImportRepo struct {
	db *gorm.DB
}

// NewZohoImportRepo returns a repo bound to db.
func NewZohoImportRepo(db *gorm.DB) *ZohoImportRepo {
	return &ZohoImportRepo{db: db}
}

// CreateUserImport inserts a per-user row. ID is generated when empty.
// IsAdmin is forced to false to preserve the singleton invariant.
func (r *ZohoImportRepo) CreateUserImport(z *db.ZohoImport) error {
	if z.ID == "" {
		z.ID = uuid.New().String()
	}
	z.IsAdmin = false
	now := time.Now()
	if z.CreatedAt.IsZero() {
		z.CreatedAt = now
	}
	z.UpdatedAt = now
	return r.db.Create(z).Error
}

// UpdateOrCreateAdmin upserts the singleton admin row. CreatedBy must be
// empty (returns ErrAdminCreatedByMustBeEmpty otherwise). Returns the stored
// row with ID and IsAdmin populated.
func (r *ZohoImportRepo) UpdateOrCreateAdmin(z *db.ZohoImport) (*db.ZohoImport, error) {
	if z.CreatedBy != "" {
		return nil, ErrAdminCreatedByMustBeEmpty
	}

	existing, err := r.GetAdmin()
	if err != nil {
		return nil, err
	}

	now := time.Now()
	if existing == nil {
		z.ID = uuid.New().String()
		z.IsAdmin = true
		z.IsActive = true
		z.CreatedAt = now
		z.UpdatedAt = now
		if err := r.db.Create(z).Error; err != nil {
			return nil, fmt.Errorf("create admin: %w", err)
		}
		return z, nil
	}

	existing.Name = z.Name
	existing.URL = z.URL
	existing.AuthHeaders = z.AuthHeaders
	existing.IsActive = true
	existing.UpdatedAt = now
	if err := r.db.Save(existing).Error; err != nil {
		return nil, fmt.Errorf("update admin: %w", err)
	}
	return existing, nil
}

// GetAdmin returns the oldest active admin row, or (nil, nil) when none exists.
func (r *ZohoImportRepo) GetAdmin() (*db.ZohoImport, error) {
	var out db.ZohoImport
	err := r.db.Where("is_admin = ? AND is_active = ?", true, true).
		Order("created_at ASC").
		First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// DeleteAdmin removes the singleton admin row(s). No-op when none exist.
func (r *ZohoImportRepo) DeleteAdmin() error {
	return r.db.Where("is_admin = ?", true).Delete(&db.ZohoImport{}).Error
}

// FindUserImportByEmail returns the oldest active per-user import whose
// created_by matches email (case-insensitive). Returns (nil, nil) when not found.
func (r *ZohoImportRepo) FindUserImportByEmail(email string) (*db.ZohoImport, error) {
	var out db.ZohoImport
	err := r.db.
		Where("is_admin = ? AND is_active = ? AND LOWER(created_by) = LOWER(?)", false, true, email).
		Order("created_at ASC").
		First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}
