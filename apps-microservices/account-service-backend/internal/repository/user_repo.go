package repository

import (
	"errors"
	"time"

	"account-service/internal/db"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

type UserRepo struct {
	g           *gorm.DB
	adminEmails map[string]struct{}
}

func NewUserRepo(g *gorm.DB, adminEmails []string) *UserRepo {
	set := make(map[string]struct{}, len(adminEmails))
	for _, e := range adminEmails {
		set[e] = struct{}{}
	}
	return &UserRepo{g: g, adminEmails: set}
}

func (r *UserRepo) UpsertOnLogin(email, displayName string) (*db.User, error) {
	now := time.Now()
	var existing db.User
	err := r.g.Where("email = ?", email).First(&existing).Error
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	if errors.Is(err, gorm.ErrRecordNotFound) {
		var count int64
		if err := r.g.Model(&db.User{}).Count(&count).Error; err != nil {
			return nil, err
		}
		_, isInAllowList := r.adminEmails[email]
		isAdmin := count == 0 || isInAllowList
		u := db.User{
			ID:          uuid.New().String(),
			Email:       email,
			DisplayName: displayName,
			IsAdmin:     isAdmin,
			IsAllowed:   true,
			LastLoginAt: &now,
		}
		if err := r.g.Create(&u).Error; err != nil {
			return nil, err
		}
		return &u, nil
	}
	existing.DisplayName = displayName
	existing.LastLoginAt = &now
	if err := r.g.Save(&existing).Error; err != nil {
		return nil, err
	}
	return &existing, nil
}

func (r *UserRepo) FindByEmail(email string) (*db.User, error) {
	var u db.User
	if err := r.g.Where("email = ?", email).First(&u).Error; err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UserRepo) List(limit, offset int) ([]db.User, int64, error) {
	var users []db.User
	var total int64
	if err := r.g.Model(&db.User{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	if err := r.g.Order("created_at DESC").Limit(limit).Offset(offset).Find(&users).Error; err != nil {
		return nil, 0, err
	}
	return users, total, nil
}

func (r *UserRepo) SetAdmin(email string, admin bool) error {
	return r.g.Model(&db.User{}).Where("email = ?", email).Update("is_admin", admin).Error
}

func (r *UserRepo) SetAllowed(email string, allowed bool) error {
	return r.g.Model(&db.User{}).Where("email = ?", email).Update("is_allowed", allowed).Error
}

// ListAllowed returns every user with is_allowed=true, newest first.
// Used by the bulk MCP sync (blocked users are not pushed to the gateway).
func (r *UserRepo) ListAllowed() ([]db.User, error) {
	var users []db.User
	if err := r.g.Where("is_allowed = ?", true).Order("created_at DESC").Find(&users).Error; err != nil {
		return nil, err
	}
	return users, nil
}
