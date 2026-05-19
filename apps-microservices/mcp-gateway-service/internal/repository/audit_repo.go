package repository

import (
	"mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// AuditRepo provides insert and paginated query operations on audit_logs via GORM.
type AuditRepo struct {
	db *gorm.DB
}

// NewAuditRepo creates a new AuditRepo.
func NewAuditRepo(database *gorm.DB) *AuditRepo {
	return &AuditRepo{db: database}
}

// Insert persists a new AuditLog entry.
func (r *AuditRepo) Insert(log *db.AuditLog) error {
	return r.db.Create(log).Error
}

// AuditFilter holds filtering and pagination parameters for audit log queries.
type AuditFilter struct {
	UserEmail    string
	Action       string
	ResourceType string
	DateFrom     string // RFC3339 or MySQL datetime string; empty means no lower bound
	DateTo       string // RFC3339 or MySQL datetime string; empty means no upper bound
	Page         int
	PerPage      int
}

// AuditListResult holds a paginated list of audit log entries.
type AuditListResult struct {
	Logs  []db.AuditLog
	Total int64
	Page  int
	Pages int
}

// List returns a paginated, filtered list of AuditLog entries ordered by created_at DESC.
// Defaults to 50 records per page when AuditFilter.PerPage is zero or negative.
func (r *AuditRepo) List(f AuditFilter) (*AuditListResult, error) {
	const defaultPerPage = 50

	perPage := f.PerPage
	if perPage <= 0 {
		perPage = defaultPerPage
	}
	page := f.Page
	if page <= 0 {
		page = 1
	}

	q := r.db.Model(&db.AuditLog{})

	if f.UserEmail != "" {
		q = q.Where("user_email = ?", f.UserEmail)
	}
	if f.Action != "" {
		q = q.Where("action = ?", f.Action)
	}
	if f.ResourceType != "" {
		q = q.Where("resource_type = ?", f.ResourceType)
	}
	if f.DateFrom != "" {
		q = q.Where("created_at >= ?", f.DateFrom)
	}
	if f.DateTo != "" {
		q = q.Where("created_at <= ?", f.DateTo)
	}

	var total int64
	if err := q.Count(&total).Error; err != nil {
		return nil, err
	}

	pages := int(total) / perPage
	if int(total)%perPage != 0 {
		pages++
	}
	if pages == 0 {
		pages = 1
	}

	var logs []db.AuditLog
	offset := (page - 1) * perPage
	if err := q.Order("created_at DESC").Limit(perPage).Offset(offset).Find(&logs).Error; err != nil {
		return nil, err
	}

	return &AuditListResult{
		Logs:  logs,
		Total: total,
		Page:  page,
		Pages: pages,
	}, nil
}
