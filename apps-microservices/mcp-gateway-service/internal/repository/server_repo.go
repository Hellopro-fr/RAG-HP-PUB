package repository

import (
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// ServerRepo provides CRUD operations on MCP servers via GORM.
type ServerRepo struct {
	db        *gorm.DB
	encryptor *crypto.Encryptor // nil if encryption key not set
}

// NewServerRepo creates a new repository. encryptor may be nil if no encryption key is configured.
func NewServerRepo(database *gorm.DB, encryptor *crypto.Encryptor) *ServerRepo {
	return &ServerRepo{db: database, encryptor: encryptor}
}

// Create inserts a new MCP server with its tags.
func (r *ServerRepo) Create(srv *db.MCPServer) error {
	if err := r.EncryptAuthHeaders(srv); err != nil {
		return err
	}
	return r.db.Create(srv).Error
}

// GetByID returns a server with all associations preloaded.
func (r *ServerRepo) GetByID(id string) (*db.MCPServer, error) {
	var srv db.MCPServer
	err := r.db.
		Preload("Tools").
		Preload("Resources").
		Preload("Prompts").
		Preload("Prompts.Arguments").
		Preload("Tags").
		First(&srv, "id = ?", id).Error
	if err != nil {
		return nil, err
	}
	if err := r.decryptAuthHeaders(&srv); err != nil {
		return nil, err
	}
	return &srv, nil
}

// ListAll returns all servers with tags preloaded. Supports optional filters.
func (r *ServerRepo) ListAll(isActive *bool, tag string) ([]db.MCPServer, error) {
	q := r.db.Preload("Tags")
	if isActive != nil {
		q = q.Where("is_active = ?", *isActive)
	}
	if tag != "" {
		q = q.Where("id IN (?)",
			r.db.Model(&db.ServerTag{}).Select("server_id").Where("tag = ?", tag))
	}

	var servers []db.MCPServer
	if err := q.Find(&servers).Error; err != nil {
		return nil, err
	}
	for i := range servers {
		if err := r.decryptAuthHeaders(&servers[i]); err != nil {
			return nil, err
		}
	}
	return servers, nil
}

// ListActive returns all active servers with full associations preloaded.
func (r *ServerRepo) ListActive() ([]db.MCPServer, error) {
	var servers []db.MCPServer
	err := r.db.
		Where("is_active = ?", true).
		Preload("Tools").
		Preload("Resources").
		Preload("Prompts").
		Preload("Prompts.Arguments").
		Preload("Tags").
		Find(&servers).Error
	if err != nil {
		return nil, err
	}
	for i := range servers {
		if err := r.decryptAuthHeaders(&servers[i]); err != nil {
			return nil, err
		}
	}
	return servers, nil
}

// Update updates the specified fields of a server.
func (r *ServerRepo) Update(id string, updates map[string]interface{}) error {
	return r.db.Model(&db.MCPServer{}).Where("id = ?", id).Updates(updates).Error
}

// Delete removes a server and all its associations (CASCADE).
func (r *ServerRepo) Delete(id string) error {
	return r.db.Delete(&db.MCPServer{}, "id = ?", id).Error
}

// SetActive enables or disables a server.
func (r *ServerRepo) SetActive(id string, active bool) error {
	return r.db.Model(&db.MCPServer{}).Where("id = ?", id).Update("is_active", active).Error
}

// UpdateHealth updates the health status and last error.
func (r *ServerRepo) UpdateHealth(id string, status string, lastErr string) error {
	updates := map[string]interface{}{
		"health_status":    status,
		"last_health_check": gorm.Expr("NOW(3)"),
	}
	if lastErr != "" {
		updates["last_error"] = lastErr
	} else {
		updates["last_error"] = ""
	}
	return r.db.Model(&db.MCPServer{}).Where("id = ?", id).Updates(updates).Error
}

// SaveDiscoveredCapabilities replaces tools, resources, and prompts for a server.
// It also updates the server's discovered metadata.
func (r *ServerRepo) SaveDiscoveredCapabilities(srv *db.MCPServer) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		// Supprime les anciennes capabilities
		if err := tx.Where("server_id = ?", srv.ID).Delete(&db.ServerTool{}).Error; err != nil {
			return err
		}
		if err := tx.Where("server_id = ?", srv.ID).Delete(&db.ServerResource{}).Error; err != nil {
			return err
		}
		// Les prompt_arguments sont supprimés en CASCADE
		if err := tx.Where("server_id = ?", srv.ID).Delete(&db.ServerPrompt{}).Error; err != nil {
			return err
		}

		// Insère les nouvelles capabilities
		for i := range srv.Tools {
			srv.Tools[i].ServerID = srv.ID
			if err := tx.Create(&srv.Tools[i]).Error; err != nil {
				return err
			}
		}
		for i := range srv.Resources {
			srv.Resources[i].ServerID = srv.ID
			if err := tx.Create(&srv.Resources[i]).Error; err != nil {
				return err
			}
		}
		for i := range srv.Prompts {
			srv.Prompts[i].ServerID = srv.ID
			if err := tx.Create(&srv.Prompts[i]).Error; err != nil {
				return err
			}
		}

		// Met à jour les métadonnées du serveur
		capsRaw, _ := json.Marshal(srv.CapabilitiesRaw)
		updates := map[string]interface{}{
			"message_url":       srv.MessageURL,
			"transport_type":    srv.TransportType,
			"server_name":       srv.ServerName,
			"server_version":    srv.ServerVersion,
			"capabilities_raw":  capsRaw,
			"health_status":     "healthy",
			"last_error":        "",
			"last_discovered_at": gorm.Expr("NOW(3)"),
		}
		return tx.Model(&db.MCPServer{}).Where("id = ?", srv.ID).Updates(updates).Error
	})
}

// SaveTags replaces all tags for a server.
func (r *ServerRepo) SaveTags(id string, tags []string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("server_id = ?", id).Delete(&db.ServerTag{}).Error; err != nil {
			return err
		}
		for _, tag := range tags {
			if err := tx.Create(&db.ServerTag{ServerID: id, Tag: tag}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// ListAllTags returns all distinct tags across all servers.
func (r *ServerRepo) ListAllTags() ([]string, error) {
	var tags []string
	err := r.db.Model(&db.ServerTag{}).Distinct("tag").Order("tag").Pluck("tag", &tags).Error
	return tags, err
}

// EncryptAuthHeaders encrypts auth_headers before DB write.
func (r *ServerRepo) EncryptAuthHeaders(srv *db.MCPServer) error {
	if len(srv.AuthHeaders) == 0 {
		return nil
	}
	if r.encryptor == nil {
		return fmt.Errorf("ENCRYPTION_KEY not set, cannot store auth_headers")
	}
	encrypted, err := r.encryptor.Encrypt(srv.AuthHeaders)
	if err != nil {
		return fmt.Errorf("encrypt auth_headers: %w", err)
	}
	srv.AuthHeaders = encrypted
	return nil
}

// decryptAuthHeaders decrypts auth_headers after DB read.
func (r *ServerRepo) decryptAuthHeaders(srv *db.MCPServer) error {
	if len(srv.AuthHeaders) == 0 {
		return nil
	}
	if r.encryptor == nil {
		// Pas de clé de déchiffrement — on laisse les données chiffrées
		srv.AuthHeaders = nil
		return nil
	}
	decrypted, err := r.encryptor.Decrypt(srv.AuthHeaders)
	if err != nil {
		return fmt.Errorf("decrypt auth_headers for server %s: %w", srv.ID, err)
	}
	srv.AuthHeaders = decrypted
	return nil
}
