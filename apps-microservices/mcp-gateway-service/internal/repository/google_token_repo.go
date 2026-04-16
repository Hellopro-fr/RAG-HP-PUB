package repository

import (
	"errors"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// GoogleTokenRepo provides CRUD operations for per-user Google OAuth2 tokens.
type GoogleTokenRepo struct {
	db        *gorm.DB
	encryptor *crypto.Encryptor
}

// NewGoogleTokenRepo creates a new GoogleTokenRepo.
func NewGoogleTokenRepo(database *gorm.DB, encryptor *crypto.Encryptor) *GoogleTokenRepo {
	return &GoogleTokenRepo{db: database, encryptor: encryptor}
}

// Create stores a new Google token record. Tokens are encrypted if an encryptor is configured.
func (r *GoogleTokenRepo) Create(token *db.UserGoogleToken) error {
	if token.ID == "" {
		token.ID = uuid.New().String()
	}
	if r.encryptor != nil {
		var err error
		token.AccessToken, err = r.encryptor.Encrypt(token.AccessToken)
		if err != nil {
			return err
		}
		token.RefreshToken, err = r.encryptor.Encrypt(token.RefreshToken)
		if err != nil {
			return err
		}
	}
	return r.db.Create(token).Error
}

// GetByUserID returns the Google token for the given gateway user ID.
// Returns nil, nil if no token is found.
func (r *GoogleTokenRepo) GetByUserID(userID uint64) (*db.UserGoogleToken, error) {
	var token db.UserGoogleToken
	err := r.db.Where("user_id = ?", userID).First(&token).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	// Decrypt tokens
	if r.encryptor != nil {
		var decErr error
		token.AccessToken, decErr = r.encryptor.Decrypt(token.AccessToken)
		if decErr != nil {
			return nil, decErr
		}
		token.RefreshToken, decErr = r.encryptor.Decrypt(token.RefreshToken)
		if decErr != nil {
			return nil, decErr
		}
	}
	return &token, nil
}

// Update updates the access token, refresh token, and expiry for an existing record.
// The caller must pass plaintext tokens; they are encrypted before writing.
func (r *GoogleTokenRepo) Update(token *db.UserGoogleToken) error {
	accessToken := token.AccessToken
	refreshToken := token.RefreshToken
	if r.encryptor != nil {
		var err error
		accessToken, err = r.encryptor.Encrypt(accessToken)
		if err != nil {
			return err
		}
		refreshToken, err = r.encryptor.Encrypt(refreshToken)
		if err != nil {
			return err
		}
	}
	return r.db.Model(token).Updates(map[string]interface{}{
		"access_token":  accessToken,
		"refresh_token": refreshToken,
		"token_expiry":  token.TokenExpiry,
		"email":         token.Email,
	}).Error
}

// DeleteByUserID removes the Google token for the given user.
func (r *GoogleTokenRepo) DeleteByUserID(userID uint64) error {
	return r.db.Where("user_id = ?", userID).Delete(&db.UserGoogleToken{}).Error
}
