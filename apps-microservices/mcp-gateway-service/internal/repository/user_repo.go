package repository

import (
	"errors"
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// UserRepo provides CRUD operations on gateway users via GORM.
type UserRepo struct {
	db          *gorm.DB
	adminEmails map[string]bool // emails that get admin role on first login
}

// NewUserRepo creates a new UserRepo. adminEmails are promoted to admin on first login.
func NewUserRepo(database *gorm.DB, adminEmails []string) *UserRepo {
	m := make(map[string]bool, len(adminEmails))
	for _, e := range adminEmails {
		m[e] = true
	}
	return &UserRepo{db: database, adminEmails: m}
}

// UpsertOnLogin creates or updates a GatewayUser on successful login.
// If the user does not exist, it is created with role "config-only" and login_count=1.
// If the user already exists, login_count is incremented, last_login_at and display_name are updated.
func (r *UserRepo) UpsertOnLogin(email, displayName string) (*db.GatewayUser, error) {
	now := time.Now()

	var user db.GatewayUser
	err := r.db.Where("email = ?", email).First(&user).Error
	if err != nil {
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, err
		}
		// Create new user — admin if in ADMIN_EMAILS, otherwise config-only.
		role := "config-only"
		if r.adminEmails[email] {
			role = "admin"
		}
		user = db.GatewayUser{
			Email:       email,
			DisplayName: displayName,
			Role:        role,
			LoginCount:  1,
			LastLoginAt: &now,
		}
		if createErr := r.db.Create(&user).Error; createErr != nil {
			return nil, createErr
		}
		return &user, nil
	}

	// Update existing user.
	updates := map[string]interface{}{
		"display_name":  displayName,
		"login_count":   gorm.Expr("login_count + 1"),
		"last_login_at": now,
	}
	if updateErr := r.db.Model(&user).Updates(updates).Error; updateErr != nil {
		return nil, updateErr
	}

	// Reload to get the updated login_count value.
	if reloadErr := r.db.Where("email = ?", email).First(&user).Error; reloadErr != nil {
		return nil, reloadErr
	}
	return &user, nil
}

// GetByEmail returns the GatewayUser with the given email.
// Returns nil, nil if no user is found.
func (r *UserRepo) GetByEmail(email string) (*db.GatewayUser, error) {
	var user db.GatewayUser
	err := r.db.Where("email = ?", email).First(&user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &user, nil
}

// ListAll returns all GatewayUsers ordered by created_at DESC.
// If role is non-empty, only users with that role are returned.
func (r *UserRepo) ListAll(role string) ([]db.GatewayUser, error) {
	q := r.db.Order("created_at DESC")
	if role != "" {
		q = q.Where("role = ?", role)
	}
	var users []db.GatewayUser
	if err := q.Find(&users).Error; err != nil {
		return nil, err
	}
	return users, nil
}

// GetByID returns the GatewayUser with the given ID.
func (r *UserRepo) GetByID(id uint64) (*db.GatewayUser, error) {
	var user db.GatewayUser
	if err := r.db.First(&user, id).Error; err != nil {
		return nil, err
	}
	return &user, nil
}

// UpdateRole sets the role field of a user.
func (r *UserRepo) UpdateRole(id uint64, role string) error {
	return r.db.Model(&db.GatewayUser{}).Where("id = ?", id).Update("role", role).Error
}

// Delete removes a GatewayUser by ID.
func (r *UserRepo) Delete(id uint64) error {
	return r.db.Delete(&db.GatewayUser{}, id).Error
}
