package repository

import (
	"encoding/json"
	"fmt"
	"log"

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
// If createdBy is non-empty, only servers created by that user are returned.
func (r *ServerRepo) ListAll(isActive *bool, tag string, createdBy string) ([]db.MCPServer, error) {
	q := r.db.Preload("Tags").Preload("Tools")
	if isActive != nil {
		q = q.Where("is_active = ?", *isActive)
	}
	if tag != "" {
		q = q.Where("id IN (?)",
			r.db.Model(&db.ServerTag{}).Select("server_id").Where("tag = ?", tag))
	}
	if createdBy != "" {
		q = q.Where("created_by = ? OR created_by = ''", createdBy)
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

// UpdateURL sets the URL column (used when the templates feature learns the
// dynamic port from the runner after initial insert).
func (r *ServerRepo) UpdateURL(id, url string) error {
	return r.db.Model(&db.MCPServer{}).Where("id = ?", id).Update("url", url).Error
}

// GetURL fetches just the URL column — avoids the tools/resources/prompts/tags
// preload that GetByID triggers when all the caller needs is the address.
func (r *ServerRepo) GetURL(id string) (string, error) {
	var url string
	err := r.db.Model(&db.MCPServer{}).Where("id = ?", id).Select("url").Scan(&url).Error
	return url, err
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

// SetToolActive enables or disables a specific tool within a server.
func (r *ServerRepo) SetToolActive(serverID string, toolName string, active bool) error {
	return r.db.Model(&db.ServerTool{}).
		Where("server_id = ? AND name = ?", serverID, toolName).
		Update("is_active", active).Error
}

// SaveDiscoveredCapabilities replaces tools, resources, and prompts for a server.
// It also updates the server's discovered metadata.
// Tool is_active status is preserved across rediscovery for tools that already exist.
func (r *ServerRepo) SaveDiscoveredCapabilities(srv *db.MCPServer) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		// Snapshot existing tool active states before deletion
		var existingTools []db.ServerTool
		tx.Where("server_id = ?", srv.ID).Find(&existingTools)
		toolActiveState := make(map[string]bool, len(existingTools))
		for _, t := range existingTools {
			toolActiveState[t.Name] = t.IsActive
			if !t.IsActive {
				log.Printf("[repo] snapshot: tool %s is_active=%v (server %s)", t.Name, t.IsActive, srv.ID)
			}
		}

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

		// Insère les nouvelles capabilities, preserving is_active for existing tools
		for i := range srv.Tools {
			srv.Tools[i].ServerID = srv.ID
			if wasActive, existed := toolActiveState[srv.Tools[i].Name]; existed {
				srv.Tools[i].IsActive = wasActive
				if !wasActive {
					log.Printf("[repo] preserving: tool %s is_active=%v (server %s)", srv.Tools[i].Name, wasActive, srv.ID)
				}
			} else {
				srv.Tools[i].IsActive = true // new tools default to active
				log.Printf("[repo] new tool: %s (server %s), not in snapshot, defaulting to active", srv.Tools[i].Name, srv.ID)
			}
			if err := tx.Exec(
				"INSERT INTO server_tools (server_id, name, description, input_schema, is_active) VALUES (?, ?, ?, ?, ?)",
				srv.Tools[i].ServerID,
				srv.Tools[i].Name,
				srv.Tools[i].Description,
				srv.Tools[i].InputSchema,
				srv.Tools[i].IsActive,
			).Error; err != nil {
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

// ClearCapabilities removes all tools, resources, and prompts for a server
// and resets discovered metadata. Used when discovery fails.
func (r *ServerRepo) ClearCapabilities(id string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("server_id = ?", id).Delete(&db.ServerTool{}).Error; err != nil {
			return err
		}
		if err := tx.Where("server_id = ?", id).Delete(&db.ServerResource{}).Error; err != nil {
			return err
		}
		if err := tx.Where("server_id = ?", id).Delete(&db.ServerPrompt{}).Error; err != nil {
			return err
		}
		return nil
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

// ListWithDocs returns all active servers that have a doc_slug set AND are
// not backed by a template instance. Template-backed servers are excluded
// from the public docs index even if they somehow have a doc_slug (e.g.
// legacy rows created before docs were off-by-default for templates) —
// their documentation lives in the template catalog, not the per-instance
// docs pages.
func (r *ServerRepo) ListWithDocs() ([]db.MCPServer, error) {
	var servers []db.MCPServer
	err := r.db.
		Where("is_active = ? AND doc_slug != '' AND doc_slug IS NOT NULL", true).
		Where("id NOT IN (SELECT mcp_server_id FROM template_instances)").
		Preload("Tools").
		Find(&servers).Error
	return servers, err
}

// GetByDocSlug returns a server by its documentation slug.
func (r *ServerRepo) GetByDocSlug(slug string) (*db.MCPServer, error) {
	var srv db.MCPServer
	err := r.db.
		Where("doc_slug = ?", slug).
		Preload("Tools").
		First(&srv).Error
	if err != nil {
		return nil, err
	}
	return &srv, nil
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
