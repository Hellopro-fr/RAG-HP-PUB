package repository

import (
	"errors"
	"time"

	"mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// UserRepo provides CRUD operations on gateway users via GORM.
type UserRepo struct {
	db            *gorm.DB
	adminEmails   map[string]bool // emails that get admin role on first login
	allowedEmails map[string]bool // emails that are allowed by default (from ALLOWED_EMAILS env)
}

// NewUserRepo creates a new UserRepo. adminEmails are promoted to admin on first login.
// allowedEmails are marked as is_allowed=true on first login.
func NewUserRepo(database *gorm.DB, adminEmails, allowedEmails []string) *UserRepo {
	am := make(map[string]bool, len(adminEmails))
	for _, e := range adminEmails {
		am[e] = true
	}
	al := make(map[string]bool, len(allowedEmails))
	for _, e := range allowedEmails {
		al[e] = true
	}
	return &UserRepo{db: database, adminEmails: am, allowedEmails: al}
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
		// is_allowed defaults to true for ADMIN_EMAILS and ALLOWED_EMAILS, false otherwise.
		role := "config-only"
		if r.adminEmails[email] {
			role = "admin"
		}
		isAllowed := r.adminEmails[email] || r.allowedEmails[email]
		user = db.GatewayUser{
			Email:       email,
			DisplayName: displayName,
			Role:        role,
			IsAllowed:   isAllowed,
			LoginCount:  1,
			LastLoginAt: &now,
		}
		if createErr := r.db.Create(&user).Error; createErr != nil {
			return nil, createErr
		}
		return &user, nil
	}

	// Update existing user.
	// If the user is in ALLOWED_EMAILS or ADMIN_EMAILS but was previously blocked,
	// automatically re-authorize them (env list takes precedence over manual block).
	updates := map[string]interface{}{
		"display_name":  displayName,
		"login_count":   gorm.Expr("login_count + 1"),
		"last_login_at": now,
	}
	if (r.allowedEmails[email] || r.adminEmails[email]) && !user.IsAllowed {
		updates["is_allowed"] = true
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

// UpdateAllowed sets the is_allowed field of a user.
func (r *UserRepo) UpdateAllowed(id uint64, isAllowed bool) error {
	return r.db.Model(&db.GatewayUser{}).Where("id = ?", id).Update("is_allowed", isAllowed).Error
}

// Delete removes a GatewayUser by ID.
func (r *UserRepo) Delete(id uint64) error {
	return r.db.Delete(&db.GatewayUser{}, id).Error
}

// SyncUserInput is one user pushed from account-service via the internal
// sync endpoint.
type SyncUserInput struct {
	Email       string
	DisplayName string
}

// SyncUsers creates a gateway user for every input email that does not exist
// yet (role config-only, is_allowed=false) and skips existing ones untouched.
// Returns the emails created and skipped. Both slices are always non-nil so
// callers can JSON-encode them as [] rather than null.
func (r *UserRepo) SyncUsers(users []SyncUserInput) (created, skipped []string, err error) {
	created = []string{}
	skipped = []string{}
	for _, u := range users {
		existing, getErr := r.GetByEmail(u.Email)
		if getErr != nil {
			return nil, nil, getErr
		}
		if existing != nil {
			skipped = append(skipped, u.Email)
			continue
		}
		newUser := db.GatewayUser{
			Email:       u.Email,
			DisplayName: u.DisplayName,
			Role:        "config-only",
			IsAllowed:   false,
		}
		if createErr := r.db.Create(&newUser).Error; createErr != nil {
			// Unique-constraint race: the user logged in (UpsertOnLogin)
			// between our lookup and insert. Re-check and treat as skipped.
			if again, _ := r.GetByEmail(u.Email); again != nil {
				skipped = append(skipped, u.Email)
				continue
			}
			return nil, nil, createErr
		}
		created = append(created, u.Email)
	}
	return created, skipped, nil
}
