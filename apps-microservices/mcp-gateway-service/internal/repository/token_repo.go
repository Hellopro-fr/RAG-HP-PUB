package repository

import (
	"context"
	"errors"

	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// ErrBDDTableNotFound is returned when a UpdateBDDTables call references
// a bdd_used_tables.id that does not exist. Callers should map this to a
// 400 response.
var ErrBDDTableNotFound = errors.New("bdd: used-table not found")

// TokenRepo handles CRUD for scope tokens.
type TokenRepo struct {
	db        *gorm.DB
	encryptor *crypto.Encryptor // nil if encryption key not set
}

func NewTokenRepo(d *gorm.DB, encryptor *crypto.Encryptor) *TokenRepo {
	return &TokenRepo{db: d, encryptor: encryptor}
}

// Create persists a new scope token with its server associations.
// If an encryptor is configured, encrypts the token before storing.
func (r *TokenRepo) Create(token *db.ScopeToken) error {
	if r.encryptor != nil && len(token.EncryptedToken) > 0 {
		encrypted, err := r.encryptor.Encrypt(token.EncryptedToken)
		if err != nil {
			return err
		}
		token.EncryptedToken = encrypted
	}
	return r.db.Create(token).Error
}

// DecryptToken decrypts the stored token. Returns empty string if not available.
func (r *TokenRepo) DecryptToken(token *db.ScopeToken) string {
	if r.encryptor == nil || len(token.EncryptedToken) == 0 {
		return ""
	}
	plaintext, err := r.encryptor.Decrypt(token.EncryptedToken)
	if err != nil {
		return ""
	}
	return string(plaintext)
}

// GetByID returns a token with its server, tool, and BDD-table associations.
func (r *TokenRepo) GetByID(id string) (*db.ScopeToken, error) {
	var token db.ScopeToken
	err := r.db.Preload("Servers").Preload("Tools").Preload("Instructions").Preload("BDDTables").Where("id = ?", id).First(&token).Error
	if err != nil {
		return nil, err
	}
	return &token, nil
}

// ListAll returns all scope tokens with server, tool, and BDD-table associations.
func (r *TokenRepo) ListAll(createdBy string) ([]db.ScopeToken, error) {
	q := r.db.Preload("Servers").Preload("Tools").Preload("Instructions").Preload("BDDTables").Order("created_at DESC")
	if createdBy != "" {
		q = q.Where("created_by = ? OR created_by = ''", createdBy)
	}
	var tokens []db.ScopeToken
	err := q.Find(&tokens).Error
	return tokens, err
}

// FindByHash looks up a token by its SHA-256 hash. This is the hot-path lookup.
func (r *TokenRepo) FindByHash(hash string) (*db.ScopeToken, error) {
	var token db.ScopeToken
	err := r.db.Preload("Servers").Preload("Tools").Preload("Instructions").Preload("BDDTables").Where("token_hash = ?", hash).First(&token).Error
	if err != nil {
		return nil, err
	}
	return &token, nil
}

// Update updates the specified fields of a token.
func (r *TokenRepo) Update(id string, updates map[string]interface{}) error {
	return r.db.Model(&db.ScopeToken{}).Where("id = ?", id).Updates(updates).Error
}

// UpdateServers replaces the server associations for a token.
func (r *TokenRepo) UpdateServers(tokenID string, serverIDs []string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		// Delete existing associations
		if err := tx.Where("token_id = ?", tokenID).Delete(&db.ScopeTokenServer{}).Error; err != nil {
			return err
		}
		// Insert new ones
		for _, sid := range serverIDs {
			if err := tx.Create(&db.ScopeTokenServer{TokenID: tokenID, ServerID: sid}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// UpdateBDDTables replaces the set of BDD used-table IDs allowed for a token.
// An empty slice clears the filter (full access). All passed IDs must already
// exist in bdd_used_tables — otherwise ErrBDDTableNotFound is returned and no
// rows are mutated. The whole operation runs in a single transaction.
//
// Duplicate IDs in the input are silently deduplicated. Without this, a
// payload like ["a","a"] would pass the count check (DISTINCT count = 1)
// against len = 2 and trip ErrBDDTableNotFound — a misleading error
// since the IDs do exist.
func (r *TokenRepo) UpdateBDDTables(ctx context.Context, tokenID string, usedTableIDs []string) error {
	usedTableIDs = dedupeIDs(usedTableIDs)
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if len(usedTableIDs) > 0 {
			var count int64
			if err := tx.Model(&db.BDDUsedTable{}).
				Where("id IN ?", usedTableIDs).
				Count(&count).Error; err != nil {
				return err
			}
			if int(count) != len(usedTableIDs) {
				return ErrBDDTableNotFound
			}
		}

		if err := tx.Where("token_id = ?", tokenID).Delete(&db.ScopeTokenBDDTable{}).Error; err != nil {
			return err
		}
		for _, id := range usedTableIDs {
			if err := tx.Create(&db.ScopeTokenBDDTable{TokenID: tokenID, UsedTableID: id}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// dedupeIDs returns ids with duplicates removed, preserving first-seen
// order. Returns nil for nil input. Shared by UpdateBDDTables on both
// the token and OAuth2 repos.
func dedupeIDs(ids []string) []string {
	if len(ids) == 0 {
		return ids
	}
	seen := make(map[string]struct{}, len(ids))
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	return out
}

// UpdateTools replaces the tool associations for a token.
func (r *TokenRepo) UpdateTools(tokenID string, tools []db.ScopeTokenTool) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		// Delete existing tool associations
		if err := tx.Where("token_id = ?", tokenID).Delete(&db.ScopeTokenTool{}).Error; err != nil {
			return err
		}
		// Insert new ones
		for _, t := range tools {
			if err := tx.Create(&t).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// Delete removes a scope token by ID (CASCADE deletes server and tool associations).
func (r *TokenRepo) Delete(id string) error {
	return r.db.Delete(&db.ScopeToken{}, "id = ?", id).Error
}

// SetActive updates the is_active flag of a token.
func (r *TokenRepo) SetActive(id string, active bool) error {
	return r.db.Model(&db.ScopeToken{}).Where("id = ?", id).Update("is_active", active).Error
}
