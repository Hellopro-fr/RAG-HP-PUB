package repository

import (
	"fmt"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// TemplateRepo provides read-only access to the seed-data templates catalog.
type TemplateRepo struct {
	db *gorm.DB
}

// NewTemplateRepo creates a new repository for read access to the templates catalog.
func NewTemplateRepo(database *gorm.DB) *TemplateRepo {
	return &TemplateRepo{db: database}
}

// ListActive returns templates where is_active = true, ordered by name.
func (r *TemplateRepo) ListActive() ([]db.Template, error) {
	var out []db.Template
	err := r.db.Where("is_active = ?", true).Order("name ASC").Find(&out).Error
	return out, err
}

// GetBySlug returns a single active template by slug. Returns gorm.ErrRecordNotFound
// when the slug does not exist or the template is inactive.
func (r *TemplateRepo) GetBySlug(slug string) (*db.Template, error) {
	var t db.Template
	if err := r.db.First(&t, "slug = ? AND is_active = ?", slug, true).Error; err != nil {
		return nil, err
	}
	return &t, nil
}

// ListAll returns every template row, active + inactive, ordered by slug.
// Used by the export handler; routine catalog listing should keep using
// ListActive so inactive seeds stay hidden from the UI.
func (r *TemplateRepo) ListAll() ([]db.Template, error) {
	var out []db.Template
	err := r.db.Order("slug ASC").Find(&out).Error
	return out, err
}

// Upsert creates each template by slug or overwrites the existing row.
// Runs in a single transaction — either all rows apply or none do. The
// caller must pre-validate required fields (slug, name, stdio_command).
func (r *TemplateRepo) Upsert(tpls []db.Template) error {
	if len(tpls) == 0 {
		return nil
	}
	return r.db.Transaction(func(tx *gorm.DB) error {
		return tx.Clauses(clause.OnConflict{
			Columns: []clause.Column{{Name: "slug"}},
			DoUpdates: clause.AssignmentColumns([]string{
				"name",
				"description",
				"icon",
				"stdio_command",
				"stdio_args",
				"default_env",
				"required_extra_env",
				"tool_prefix",
				"tags",
				"is_active",
				"kind",
				"updated_at",
			}),
		}).Create(&tpls).Error
	})
}

// InstanceRepo manages TemplateInstance rows. All writes encrypt the
// service-account JSON at rest; deletes are transactional with mcp_servers so
// the pre-delete runner-kill step cannot be silently skipped.
type InstanceRepo struct {
	db        *gorm.DB
	encryptor *crypto.Encryptor // must be non-nil (encryption is mandatory here)
}

// NewInstanceRepo creates a repository for TemplateInstance rows. The encryptor
// is required — callers that pass nil will get an error on Create.
func NewInstanceRepo(database *gorm.DB, encryptor *crypto.Encryptor) *InstanceRepo {
	return &InstanceRepo{db: database, encryptor: encryptor}
}

// Create inserts a new template instance with its SA JSON encrypted at rest.
// inst.EncryptedCredentials is populated by this call; callers should not set it.
func (r *InstanceRepo) Create(inst *db.TemplateInstance, credentialsPlain []byte) error {
	if r.encryptor == nil {
		return fmt.Errorf("encryptor required for template instances")
	}
	ct, err := r.encryptor.Encrypt(credentialsPlain)
	if err != nil {
		return fmt.Errorf("encrypt credentials: %w", err)
	}
	inst.EncryptedCredentials = ct
	return r.db.Create(inst).Error
}

// GetByIDWithCredentials returns the instance along with the decrypted SA JSON.
// Callers that do not need the secret should use GetByID instead.
func (r *InstanceRepo) GetByIDWithCredentials(id string) (*db.TemplateInstance, []byte, error) {
	if r.encryptor == nil {
		return nil, nil, fmt.Errorf("encryptor required for template instances")
	}
	var inst db.TemplateInstance
	if err := r.db.First(&inst, "id = ?", id).Error; err != nil {
		return nil, nil, err
	}
	plain, err := r.encryptor.Decrypt(inst.EncryptedCredentials)
	if err != nil {
		return nil, nil, fmt.Errorf("decrypt: %w", err)
	}
	return &inst, plain, nil
}

// GetByID returns the instance without decrypting credentials.
func (r *InstanceRepo) GetByID(id string) (*db.TemplateInstance, error) {
	var inst db.TemplateInstance
	if err := r.db.First(&inst, "id = ?", id).Error; err != nil {
		return nil, err
	}
	return &inst, nil
}

// FindByMCPServerID looks up the template instance that backs a given
// mcp_servers row. Returns gorm.ErrRecordNotFound when the server isn't
// template-backed — callers distinguish that from other DB errors.
func (r *InstanceRepo) FindByMCPServerID(serverID string) (*db.TemplateInstance, error) {
	var inst db.TemplateInstance
	if err := r.db.First(&inst, "mcp_server_id = ?", serverID).Error; err != nil {
		return nil, err
	}
	return &inst, nil
}

// ListAll returns all template instances, newest first.
func (r *InstanceRepo) ListAll() ([]db.TemplateInstance, error) {
	var out []db.TemplateInstance
	err := r.db.Order("created_at DESC").Find(&out).Error
	return out, err
}

// ListByTemplate returns instances filtered by template slug, newest first.
func (r *InstanceRepo) ListByTemplate(slug string) ([]db.TemplateInstance, error) {
	var out []db.TemplateInstance
	err := r.db.Where("template_slug = ?", slug).Order("created_at DESC").Find(&out).Error
	return out, err
}

// CountsByTemplate returns {template_slug → number of instances}.
func (r *InstanceRepo) CountsByTemplate() (map[string]int, error) {
	var rows []struct {
		TemplateSlug string
		Cnt          int
	}
	err := r.db.Model(&db.TemplateInstance{}).
		Select("template_slug, COUNT(*) as cnt").
		Group("template_slug").
		Scan(&rows).Error
	if err != nil {
		return nil, err
	}
	m := make(map[string]int, len(rows))
	for _, row := range rows {
		m[row.TemplateSlug] = row.Cnt
	}
	return m, nil
}

// UpdateStatus updates the runner_status / runner_last_error / runner_port fields.
// Pass port = nil to keep the existing port value.
func (r *InstanceRepo) UpdateStatus(id, status, lastError string, port *int) error {
	updates := map[string]any{
		"runner_status":     status,
		"runner_last_error": lastError,
	}
	if port != nil {
		updates["runner_port"] = *port
	}
	result := r.db.Model(&db.TemplateInstance{}).Where("id = ?", id).Updates(updates)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

// UpdateCredentials re-encrypts and stores a new SA JSON + its hash.
func (r *InstanceRepo) UpdateCredentials(id string, credentialsPlain []byte, hashHex string) error {
	if r.encryptor == nil {
		return fmt.Errorf("encryptor required for template instances")
	}
	ct, err := r.encryptor.Encrypt(credentialsPlain)
	if err != nil {
		return fmt.Errorf("encrypt: %w", err)
	}
	result := r.db.Model(&db.TemplateInstance{}).Where("id = ?", id).Updates(map[string]any{
		"encrypted_credentials": ct,
		"credentials_hash":      hashHex,
	})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

// DeleteWithMCPServer removes both the template_instances row and its linked
// mcp_servers row in a single transaction. The transaction ensures that the
// runner-kill step (which the handler does before calling us) is not silently
// skipped by a raw DELETE against mcp_servers. Cascades on mcp_servers cover
// tools, resources, prompts, tags, and scope/oauth2 join tables as usual.
func (r *InstanceRepo) DeleteWithMCPServer(id string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		var inst db.TemplateInstance
		if err := tx.First(&inst, "id = ?", id).Error; err != nil {
			return err
		}
		if err := tx.Delete(&inst).Error; err != nil {
			return err
		}
		return tx.Delete(&db.MCPServer{}, "id = ?", inst.MCPServerID).Error
	})
}
