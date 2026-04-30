package repository

import (
	"context"

	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// OAuth2Repo handles CRUD for OAuth2 clients.
type OAuth2Repo struct {
	db        *gorm.DB
	encryptor *crypto.Encryptor // nil if encryption key not set
}

func NewOAuth2Repo(d *gorm.DB, encryptor *crypto.Encryptor) *OAuth2Repo {
	return &OAuth2Repo{db: d, encryptor: encryptor}
}

// Create persists a new OAuth2 client with its server/tool associations.
// If an encryptor is configured, encrypts the secret before storing.
func (r *OAuth2Repo) Create(client *db.OAuth2Client) error {
	if r.encryptor != nil && len(client.EncryptedSecret) > 0 {
		encrypted, err := r.encryptor.Encrypt(client.EncryptedSecret)
		if err != nil {
			return err
		}
		client.EncryptedSecret = encrypted
	}
	return r.db.Create(client).Error
}

// DecryptSecret decrypts the stored client secret. Returns empty string if not available.
func (r *OAuth2Repo) DecryptSecret(client *db.OAuth2Client) string {
	if r.encryptor == nil || len(client.EncryptedSecret) == 0 {
		return ""
	}
	plaintext, err := r.encryptor.Decrypt(client.EncryptedSecret)
	if err != nil {
		return ""
	}
	return string(plaintext)
}

// GetByID returns a client with its server, tool, and BDD-table associations.
func (r *OAuth2Repo) GetByID(id string) (*db.OAuth2Client, error) {
	var client db.OAuth2Client
	err := r.db.Preload("Servers").Preload("Tools").Preload("Instructions").Preload("BDDTables").Where("id = ?", id).First(&client).Error
	if err != nil {
		return nil, err
	}
	return &client, nil
}

// ListAll returns all OAuth2 clients with server, tool, and BDD-table associations.
func (r *OAuth2Repo) ListAll(createdBy string) ([]db.OAuth2Client, error) {
	q := r.db.Preload("Servers").Preload("Tools").Preload("Instructions").Preload("BDDTables").Order("created_at DESC")
	if createdBy != "" {
		q = q.Where("created_by = ? OR created_by = ''", createdBy)
	}
	var clients []db.OAuth2Client
	err := q.Find(&clients).Error
	return clients, err
}

// FindBySecretHash looks up a client by its SHA-256 secret hash. This is the hot-path lookup for /oauth/token.
func (r *OAuth2Repo) FindBySecretHash(hash string) (*db.OAuth2Client, error) {
	var client db.OAuth2Client
	err := r.db.Preload("Servers").Preload("Tools").Preload("Instructions").Preload("BDDTables").Where("secret_hash = ?", hash).First(&client).Error
	if err != nil {
		return nil, err
	}
	return &client, nil
}

// FindByID looks up a client by its ID (client_id) with associations. Used for access token validation.
func (r *OAuth2Repo) FindByID(id string) (*db.OAuth2Client, error) {
	return r.GetByID(id)
}

// Update updates the specified fields of a client.
func (r *OAuth2Repo) Update(id string, updates map[string]interface{}) error {
	return r.db.Model(&db.OAuth2Client{}).Where("id = ?", id).Updates(updates).Error
}

// UpdateServers replaces the server associations for a client.
func (r *OAuth2Repo) UpdateServers(clientID string, serverIDs []string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("client_id = ?", clientID).Delete(&db.OAuth2ClientServer{}).Error; err != nil {
			return err
		}
		for _, sid := range serverIDs {
			if err := tx.Create(&db.OAuth2ClientServer{ClientID: clientID, ServerID: sid}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// UpdateBDDTables replaces the set of BDD used-table IDs allowed for a client.
// An empty slice clears the filter (full access). All passed IDs must already
// exist in bdd_used_tables — otherwise ErrBDDTableNotFound is returned and no
// rows are mutated. The whole operation runs in a single transaction.
//
// Duplicate IDs in the input are silently deduplicated; see TokenRepo.UpdateBDDTables
// for the rationale.
func (r *OAuth2Repo) UpdateBDDTables(ctx context.Context, clientID string, usedTableIDs []string) error {
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

		if err := tx.Where("client_id = ?", clientID).Delete(&db.OAuth2ClientBDDTable{}).Error; err != nil {
			return err
		}
		for _, id := range usedTableIDs {
			if err := tx.Create(&db.OAuth2ClientBDDTable{ClientID: clientID, UsedTableID: id}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// UpdateTools replaces the tool associations for a client.
func (r *OAuth2Repo) UpdateTools(clientID string, tools []db.OAuth2ClientTool) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("client_id = ?", clientID).Delete(&db.OAuth2ClientTool{}).Error; err != nil {
			return err
		}
		for _, t := range tools {
			if err := tx.Create(&t).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// Delete removes an OAuth2 client by ID (CASCADE deletes server and tool associations).
func (r *OAuth2Repo) Delete(id string) error {
	return r.db.Delete(&db.OAuth2Client{}, "id = ?", id).Error
}

// SetActive updates the is_active flag of a client.
func (r *OAuth2Repo) SetActive(id string, active bool) error {
	return r.db.Model(&db.OAuth2Client{}).Where("id = ?", id).Update("is_active", active).Error
}
