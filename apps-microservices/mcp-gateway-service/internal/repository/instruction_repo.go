package repository

import (
	"sort"

	"github.com/google/uuid"
	"mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// InstructionRepo handles CRUD for reusable LLM instruction pages. Each page
// holds an ordered list of rows; each row has its own server scope.
type InstructionRepo struct {
	db *gorm.DB
}

func NewInstructionRepo(d *gorm.DB) *InstructionRepo {
	return &InstructionRepo{db: d}
}

// RowInput is the caller-facing shape for a row when creating or updating an
// instruction page. ID is optional — empty = repo assigns a fresh UUID. Kind
// defaults to "per_server" when empty; ServerIDs is ignored for general rows.
type RowInput struct {
	ID        string
	Kind      string
	Title     string
	Body      string
	ServerIDs []string
}

// InstructionUsage reports which tokens and OAuth2 clients reference a given
// instruction. Used by the admin UI to warn before destructive edits.
type InstructionUsage struct {
	TokenIDs        []string
	OAuth2ClientIDs []string
}

// Create persists a new instruction page and its rows atomically.
func (r *InstructionRepo) Create(title, description string, rows []RowInput, createdBy string) (*db.LLMInstruction, error) {
	ins := &db.LLMInstruction{
		ID:          uuid.New().String(),
		Title:       title,
		Description: description,
		CreatedBy:   createdBy,
	}
	err := r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(ins).Error; err != nil {
			return err
		}
		return insertRows(tx, ins.ID, rows)
	})
	if err != nil {
		return nil, err
	}
	return r.GetByID(ins.ID)
}

// GetByID returns a page with its rows (ordered by display_order) and each
// row's server links preloaded.
func (r *InstructionRepo) GetByID(id string) (*db.LLMInstruction, error) {
	var ins db.LLMInstruction
	err := r.db.
		Preload("Rows", func(tx *gorm.DB) *gorm.DB {
			return tx.Order("display_order ASC, id ASC")
		}).
		Preload("Rows.Servers").
		Where("id = ?", id).
		First(&ins).Error
	if err != nil {
		return nil, err
	}
	return &ins, nil
}

// List returns instruction pages newest-first with rows and row-servers
// preloaded. When createdBy is non-empty the result is scoped to pages the
// user (or legacy rows without an owner) created — mirrors tokenRepo.ListAll.
func (r *InstructionRepo) List(createdBy string) ([]db.LLMInstruction, error) {
	q := r.db.
		Preload("Rows", func(tx *gorm.DB) *gorm.DB {
			return tx.Order("display_order ASC, id ASC")
		}).
		Preload("Rows.Servers").
		Order("created_at DESC")
	if createdBy != "" {
		q = q.Where("created_by = ? OR created_by = ''", createdBy)
	}
	var out []db.LLMInstruction
	err := q.Find(&out).Error
	return out, err
}

// Update rewrites page-level fields and replaces the row set atomically. The
// old rows (and their server links) are cascade-deleted first. Row IDs from
// the caller are preserved when supplied; otherwise fresh UUIDs are minted.
func (r *InstructionRepo) Update(id, title, description string, rows []RowInput) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		updates := map[string]any{
			"title":       title,
			"description": description,
		}
		if err := tx.Model(&db.LLMInstruction{}).Where("id = ?", id).Updates(updates).Error; err != nil {
			return err
		}
		// Wipe previous rows. FK cascade removes LLMInstructionRowServer rows
		// too (on MySQL); explicit delete here keeps SQLite tests honest.
		var oldRowIDs []string
		if err := tx.Model(&db.LLMInstructionRow{}).
			Where("instruction_id = ?", id).
			Pluck("id", &oldRowIDs).Error; err != nil {
			return err
		}
		if len(oldRowIDs) > 0 {
			if err := tx.Where("row_id IN ?", oldRowIDs).Delete(&db.LLMInstructionRowServer{}).Error; err != nil {
				return err
			}
		}
		if err := tx.Where("instruction_id = ?", id).Delete(&db.LLMInstructionRow{}).Error; err != nil {
			return err
		}
		return insertRows(tx, id, rows)
	})
}

// Delete removes a page and every junction row that references it.
func (r *InstructionRepo) Delete(id string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("instruction_id = ?", id).Delete(&db.ScopeTokenInstruction{}).Error; err != nil {
			return err
		}
		if err := tx.Where("instruction_id = ?", id).Delete(&db.OAuth2ClientInstruction{}).Error; err != nil {
			return err
		}
		var rowIDs []string
		if err := tx.Model(&db.LLMInstructionRow{}).
			Where("instruction_id = ?", id).
			Pluck("id", &rowIDs).Error; err != nil {
			return err
		}
		if len(rowIDs) > 0 {
			if err := tx.Where("row_id IN ?", rowIDs).Delete(&db.LLMInstructionRowServer{}).Error; err != nil {
				return err
			}
		}
		if err := tx.Where("instruction_id = ?", id).Delete(&db.LLMInstructionRow{}).Error; err != nil {
			return err
		}
		return tx.Delete(&db.LLMInstruction{}, "id = ?", id).Error
	})
}

// ListByServerIDs returns instructions that have at least one row applicable
// to the given set — either a "general" row (applies to every scope) or a
// "per_server" row with a matching server link. Empty / nil filter returns
// an empty slice (callers must pass a concrete set; returning everything
// here would be a footgun). When createdBy is non-empty, the result is
// additionally scoped to pages owned by that user (or legacy unowned rows).
func (r *InstructionRepo) ListByServerIDs(serverIDs []string, createdBy string) ([]db.LLMInstruction, error) {
	if len(serverIDs) == 0 {
		return []db.LLMInstruction{}, nil
	}
	var ids []string
	// Union of two conditions:
	//  1. the page has any "general" row
	//  2. the page has a "per_server" row whose servers intersect serverIDs
	// A left join + OR in the WHERE captures both.
	q := r.db.
		Table("llm_instructions").
		Select("DISTINCT llm_instructions.id").
		Joins("JOIN llm_instruction_rows ON llm_instruction_rows.instruction_id = llm_instructions.id").
		Joins("LEFT JOIN llm_instruction_row_servers ON llm_instruction_row_servers.row_id = llm_instruction_rows.id").
		Where(
			"llm_instruction_rows.kind = ? OR (llm_instruction_rows.kind = ? AND llm_instruction_row_servers.server_id IN ?)",
			db.LLMInstructionRowKindGeneral,
			db.LLMInstructionRowKindPerServer,
			serverIDs,
		)
	if createdBy != "" {
		q = q.Where("llm_instructions.created_by = ? OR llm_instructions.created_by = ''", createdBy)
	}
	if err := q.Pluck("llm_instructions.id", &ids).Error; err != nil {
		return nil, err
	}
	if len(ids) == 0 {
		return []db.LLMInstruction{}, nil
	}
	var out []db.LLMInstruction
	err := r.db.
		Preload("Rows", func(tx *gorm.DB) *gorm.DB {
			return tx.Order("display_order ASC, id ASC")
		}).
		Preload("Rows.Servers").
		Where("id IN ?", ids).
		Order("created_at DESC").
		Find(&out).Error
	return out, err
}

// ResolveForToken flattens the token's picked instructions into the concrete
// set of ROWS to render, keeping only rows whose server links intersect
// allowedServerIDs. Rows are returned in (page.created_at DESC, display_order)
// order so the output is stable across sessions.
func (r *InstructionRepo) ResolveForToken(tokenID string, allowedServerIDs []string) ([]db.LLMInstructionRow, error) {
	return r.resolveForScope("scope_token_instructions", "token_id", tokenID, allowedServerIDs)
}

// ResolveForOAuth2Client is the symmetric resolver for OAuth2 clients.
func (r *InstructionRepo) ResolveForOAuth2Client(clientID string, allowedServerIDs []string) ([]db.LLMInstructionRow, error) {
	return r.resolveForScope("oauth2_client_instructions", "client_id", clientID, allowedServerIDs)
}

// ReplaceTokenInstructions atomically replaces the token's instruction links
// with the given set. Deduplicates input to keep the primary key happy.
func (r *InstructionRepo) ReplaceTokenInstructions(tokenID string, instructionIDs []string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("token_id = ?", tokenID).Delete(&db.ScopeTokenInstruction{}).Error; err != nil {
			return err
		}
		seen := make(map[string]bool, len(instructionIDs))
		for _, id := range instructionIDs {
			if id == "" || seen[id] {
				continue
			}
			seen[id] = true
			if err := tx.Create(&db.ScopeTokenInstruction{TokenID: tokenID, InstructionID: id}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// ReplaceOAuth2ClientInstructions is the symmetric operation for OAuth2 clients.
func (r *InstructionRepo) ReplaceOAuth2ClientInstructions(clientID string, instructionIDs []string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("client_id = ?", clientID).Delete(&db.OAuth2ClientInstruction{}).Error; err != nil {
			return err
		}
		seen := make(map[string]bool, len(instructionIDs))
		for _, id := range instructionIDs {
			if id == "" || seen[id] {
				continue
			}
			seen[id] = true
			if err := tx.Create(&db.OAuth2ClientInstruction{ClientID: clientID, InstructionID: id}).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// GetUsage lists the tokens and OAuth2 clients that reference this page.
func (r *InstructionRepo) GetUsage(instructionID string) (InstructionUsage, error) {
	var usage InstructionUsage
	var tokens []db.ScopeTokenInstruction
	if err := r.db.Where("instruction_id = ?", instructionID).Find(&tokens).Error; err != nil {
		return usage, err
	}
	for _, t := range tokens {
		usage.TokenIDs = append(usage.TokenIDs, t.TokenID)
	}
	var clients []db.OAuth2ClientInstruction
	if err := r.db.Where("instruction_id = ?", instructionID).Find(&clients).Error; err != nil {
		return usage, err
	}
	for _, c := range clients {
		usage.OAuth2ClientIDs = append(usage.OAuth2ClientIDs, c.ClientID)
	}
	return usage, nil
}

// ValidateForScope returns the instructionIDs that cannot be picked because
// they contain no row that would ever render for this scope — i.e. neither
// a "general" row nor a "per_server" row with a matching server link.
// Pages that contain at least one general row are always valid.
func (r *InstructionRepo) ValidateForScope(instructionIDs, allowedServerIDs []string) ([]string, error) {
	if len(instructionIDs) == 0 {
		return nil, nil
	}
	var validIDs []string
	query := r.db.
		Table("llm_instructions").
		Select("DISTINCT llm_instructions.id").
		Joins("JOIN llm_instruction_rows ON llm_instruction_rows.instruction_id = llm_instructions.id").
		Joins("LEFT JOIN llm_instruction_row_servers ON llm_instruction_row_servers.row_id = llm_instruction_rows.id").
		Where("llm_instructions.id IN ?", instructionIDs)
	if len(allowedServerIDs) == 0 {
		// No allowed servers — only pages with a general row survive.
		query = query.Where("llm_instruction_rows.kind = ?", db.LLMInstructionRowKindGeneral)
	} else {
		query = query.Where(
			"llm_instruction_rows.kind = ? OR (llm_instruction_rows.kind = ? AND llm_instruction_row_servers.server_id IN ?)",
			db.LLMInstructionRowKindGeneral,
			db.LLMInstructionRowKindPerServer,
			allowedServerIDs,
		)
	}
	if err := query.Pluck("llm_instructions.id", &validIDs).Error; err != nil {
		return nil, err
	}
	validSet := make(map[string]bool, len(validIDs))
	for _, v := range validIDs {
		validSet[v] = true
	}
	var invalid []string
	for _, id := range instructionIDs {
		if !validSet[id] {
			invalid = append(invalid, id)
		}
	}
	return invalid, nil
}

// ── internal helpers ─────────────────────────────────────────────────────────

// insertRows writes the row set for an instruction inside an open transaction.
// Callers are responsible for wiping previous rows first (Update does this).
// Assigns DisplayOrder from the caller-supplied slice order so the admin UI's
// reorder is persisted, and mints fresh UUIDs for rows that come without one.
// General rows never get server links written, even if ServerIDs is non-empty.
func insertRows(tx *gorm.DB, instructionID string, rows []RowInput) error {
	for i, in := range rows {
		rowID := in.ID
		if rowID == "" {
			rowID = uuid.New().String()
		}
		kind := in.Kind
		if kind == "" {
			kind = db.LLMInstructionRowKindPerServer
		}
		row := &db.LLMInstructionRow{
			ID:            rowID,
			InstructionID: instructionID,
			Kind:          kind,
			Title:         in.Title,
			Body:          in.Body,
			DisplayOrder:  i,
		}
		if err := tx.Create(row).Error; err != nil {
			return err
		}
		if kind == db.LLMInstructionRowKindGeneral {
			// General rows ignore server scope — no junction rows to write.
			continue
		}
		seen := make(map[string]bool, len(in.ServerIDs))
		for _, sid := range in.ServerIDs {
			if sid == "" || seen[sid] {
				continue
			}
			seen[sid] = true
			if err := tx.Create(&db.LLMInstructionRowServer{
				RowID:    rowID,
				ServerID: sid,
			}).Error; err != nil {
				return err
			}
		}
	}
	return nil
}

// resolveForScope flattens the scope's picked instructions into the concrete
// rows to render. A row is included when EITHER it is a "general" row (always
// on) OR it is a "per_server" row with a linked server in allowedServerIDs.
// Uses sort.SliceStable for (page.created_at DESC, display_order) ordering so
// composed output is stable across sessions, without relying on ORDER BY
// across a multi-table join (SQLite + GORM can be finicky).
func (r *InstructionRepo) resolveForScope(scopeTable, scopeCol, scopeID string, allowedServerIDs []string) ([]db.LLMInstructionRow, error) {
	type rowWithOrder struct {
		db.LLMInstructionRow
		InstructionCreatedAt string `gorm:"column:instruction_created_at"`
	}
	var rows []rowWithOrder
	query := r.db.
		Table("llm_instruction_rows").
		Select("DISTINCT llm_instruction_rows.*, llm_instructions.created_at AS instruction_created_at").
		Joins("JOIN llm_instructions ON llm_instructions.id = llm_instruction_rows.instruction_id").
		Joins("JOIN "+scopeTable+" sti ON sti.instruction_id = llm_instructions.id").
		Joins("LEFT JOIN llm_instruction_row_servers lrs ON lrs.row_id = llm_instruction_rows.id").
		Where("sti."+scopeCol+" = ?", scopeID)
	if len(allowedServerIDs) == 0 {
		// No allowed servers → only general rows render.
		query = query.Where("llm_instruction_rows.kind = ?", db.LLMInstructionRowKindGeneral)
	} else {
		query = query.Where(
			"llm_instruction_rows.kind = ? OR (llm_instruction_rows.kind = ? AND lrs.server_id IN ?)",
			db.LLMInstructionRowKindGeneral,
			db.LLMInstructionRowKindPerServer,
			allowedServerIDs,
		)
	}
	if err := query.Scan(&rows).Error; err != nil {
		return nil, err
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].InstructionCreatedAt != rows[j].InstructionCreatedAt {
			return rows[i].InstructionCreatedAt > rows[j].InstructionCreatedAt
		}
		return rows[i].DisplayOrder < rows[j].DisplayOrder
	})
	out := make([]db.LLMInstructionRow, len(rows))
	for i, r := range rows {
		out[i] = r.LLMInstructionRow
	}
	return out, nil
}
