package repository

import (
	"errors"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"mcp-gateway/internal/db"
)

// ServerAuthorizationRepo is the CRUD layer for the server_authorizations
// table. Enforces (server_id, email) uniqueness on insert; idempotent inserts
// silently coalesce so the admin UI can re-grant without checking first.
type ServerAuthorizationRepo struct {
	db *gorm.DB
}

func NewServerAuthorizationRepo(d *gorm.DB) *ServerAuthorizationRepo {
	return &ServerAuthorizationRepo{db: d}
}

// IsAuthorized reports whether the given email is granted full access on the
// given server. Repo errors short-circuit to false (fail-closed).
func (r *ServerAuthorizationRepo) IsAuthorized(serverID, email string) bool {
	if serverID == "" || email == "" {
		return false
	}
	var row db.ServerAuthorization
	err := r.db.Where("server_id = ? AND email = ?", serverID, email).First(&row).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return false
		}
		return false
	}
	return true
}

// Create inserts a grant. Duplicate (server_id, email) pairs are silently
// ignored via ON CONFLICT DO NOTHING.
func (r *ServerAuthorizationRepo) Create(row *db.ServerAuthorization) error {
	return r.db.Clauses(clause.OnConflict{DoNothing: true}).Create(row).Error
}

// Delete removes a grant. Missing rows are not an error.
func (r *ServerAuthorizationRepo) Delete(serverID, email string) error {
	return r.db.Where("server_id = ? AND email = ?", serverID, email).
		Delete(&db.ServerAuthorization{}).Error
}

// ListByServer returns every grant for the given server, ordered by
// created_at DESC (newest first).
func (r *ServerAuthorizationRepo) ListByServer(serverID string) ([]db.ServerAuthorization, error) {
	var rows []db.ServerAuthorization
	err := r.db.Where("server_id = ?", serverID).
		Order("created_at DESC").
		Find(&rows).Error
	return rows, err
}

// List returns every grant across every server, ordered by created_at DESC.
// Used by the admin UI overview page.
func (r *ServerAuthorizationRepo) List() ([]db.ServerAuthorization, error) {
	var rows []db.ServerAuthorization
	err := r.db.Order("created_at DESC").Find(&rows).Error
	return rows, err
}
