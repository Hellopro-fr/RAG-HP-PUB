package repository

import (
	"errors"
	"fmt"
	"strings"
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
// created_by matches email (case-insensitive). Mirrors the runtime resolver
// in mcp-zoho-service: tries exact-email first, then falls back to the
// login portion (local-part before @) so sheet-imports that stored
// created_by="alice" still resolve when the caller is alice@hp.fr.
// Returns (nil, nil) when nothing matches.
func (r *ZohoImportRepo) FindUserImportByEmail(email string) (*db.ZohoImport, error) {
	login := email
	if at := strings.IndexByte(email, '@'); at > 0 {
		login = email[:at]
	}
	var out db.ZohoImport
	err := r.db.
		Where(
			"is_admin = ? AND is_active = ? AND (LOWER(created_by) = LOWER(?) OR (? <> '' AND LOWER(created_by) = LOWER(?)))",
			false, true, email, login, login,
		).
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

// ErrZohoImportNotFound is returned by Update and DeleteByID when the target
// row does not exist.
var ErrZohoImportNotFound = errors.New("zoho_import not found")

// ZohoListFilter narrows the List query. Each field is independently
// optional: nil filters are dropped at the SQL layer.
type ZohoListFilter struct {
	IsAdmin   *bool  // nil = both
	Search    string // matches name or created_by, case-insensitive substring
	CreatedBy string // when non-empty, restricts the list to rows owned by this
	// email (plus rows with an empty created_by). Used to scope non-admin
	// callers to their own imports.
}

// ZohoUpdatePatch is the bag of optionally-set fields for Update. A nil pointer
// means "do not touch this column"; a non-nil pointer (even if pointing at an
// empty value) means "write this value, including clearing slices".
type ZohoUpdatePatch struct {
	Name        *string
	URL         *string
	AuthHeaders *[]byte
	IsActive    *bool
}

// List returns rows matching filter, paginated by page (1-indexed) and limit.
// limit is clamped to [1, 100]; page to >= 1.
func (r *ZohoImportRepo) List(filter ZohoListFilter, page, limit int) ([]db.ZohoImport, int64, error) {
	if page < 1 {
		page = 1
	}
	if limit < 1 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}

	tx := r.db.Model(&db.ZohoImport{})
	if filter.IsAdmin != nil {
		tx = tx.Where("is_admin = ?", *filter.IsAdmin)
	}
	if s := strings.TrimSpace(filter.Search); s != "" {
		like := "%" + strings.ToLower(s) + "%"
		tx = tx.Where("LOWER(name) LIKE ? OR LOWER(created_by) LIKE ?", like, like)
	}
	if filter.CreatedBy != "" {
		tx = tx.Where("created_by = ? OR created_by = ''", filter.CreatedBy)
	}

	var total int64
	if err := tx.Count(&total).Error; err != nil {
		return nil, 0, fmt.Errorf("count: %w", err)
	}

	var rows []db.ZohoImport
	if err := tx.Order("created_at DESC").
		Limit(limit).
		Offset((page - 1) * limit).
		Find(&rows).Error; err != nil {
		return nil, 0, fmt.Errorf("find: %w", err)
	}
	return rows, total, nil
}

// GetByID returns (row, nil) when found, (nil, nil) when missing, or (nil, err)
// on DB error.
func (r *ZohoImportRepo) GetByID(id string) (*db.ZohoImport, error) {
	var out db.ZohoImport
	err := r.db.Where("id = ?", id).First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// Update applies a patch. Each non-nil patch field is written.
// Returns ErrZohoImportNotFound when id doesn't match.
func (r *ZohoImportRepo) Update(id string, patch ZohoUpdatePatch) (*db.ZohoImport, error) {
	row, err := r.GetByID(id)
	if err != nil {
		return nil, err
	}
	if row == nil {
		return nil, ErrZohoImportNotFound
	}
	if patch.Name != nil {
		row.Name = *patch.Name
	}
	if patch.URL != nil {
		row.URL = *patch.URL
	}
	if patch.AuthHeaders != nil {
		if len(*patch.AuthHeaders) == 0 {
			row.AuthHeaders = nil
		} else {
			row.AuthHeaders = *patch.AuthHeaders
		}
	}
	if patch.IsActive != nil {
		row.IsActive = *patch.IsActive
	}
	row.UpdatedAt = time.Now()
	if err := r.db.Save(row).Error; err != nil {
		return nil, fmt.Errorf("save: %w", err)
	}
	return row, nil
}

// DeleteByID removes row id. Returns ErrZohoImportNotFound when missing.
func (r *ZohoImportRepo) DeleteByID(id string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		res := tx.Where("id = ?", id).Delete(&db.ZohoImport{})
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return ErrZohoImportNotFound
		}
		return tx.Where("import_id = ?", id).Delete(&db.ZohoImportTool{}).Error
	})
}

// ReplaceTools atomically replaces every tool row attached to importID with
// the supplied slice. Empty tools deletes the catalog without re-inserting,
// matching the "discovery returned zero tools" path. Returns the number of
// rows finally present (== len(tools) on success). Caller must already have
// validated importID exists.
func (r *ZohoImportRepo) ReplaceTools(importID string, tools []db.ZohoImportTool) (int, error) {
	if importID == "" {
		return 0, fmt.Errorf("import id required")
	}
	err := r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("import_id = ?", importID).Delete(&db.ZohoImportTool{}).Error; err != nil {
			return err
		}
		if len(tools) == 0 {
			return nil
		}
		now := time.Now()
		for i := range tools {
			tools[i].ImportID = importID
			tools[i].ID = 0
			tools[i].CreatedAt = now
			tools[i].UpdatedAt = now
		}
		return tx.Create(&tools).Error
	})
	if err != nil {
		return 0, err
	}
	return len(tools), nil
}

// ListTools returns the persisted tool catalog for a given import row in a
// stable (name ASC) order. Returns an empty slice (never nil) when the
// import has no tools — caller treats that as "fall back to admin row".
func (r *ZohoImportRepo) ListTools(importID string) ([]db.ZohoImportTool, error) {
	if importID == "" {
		return []db.ZohoImportTool{}, nil
	}
	var rows []db.ZohoImportTool
	if err := r.db.Where("import_id = ?", importID).Order("name ASC").Find(&rows).Error; err != nil {
		return nil, err
	}
	if rows == nil {
		rows = []db.ZohoImportTool{}
	}
	return rows, nil
}
