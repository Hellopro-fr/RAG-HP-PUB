package repository

import (
	"context"
	"errors"
	"strings"

	"github.com/go-sql-driver/mysql"
	"github.com/google/uuid"
	"gorm.io/gorm"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// Sentinel errors surfaced by BDDUsedRepo. Callers should rely on
// errors.Is to match these (driver-specific causes are wrapped).
var (
	ErrBDDNotFound       = errors.New("bdd used: not found")
	ErrBDDDuplicateTable = errors.New("bdd used: duplicate table")
	ErrBDDDuplicateField = errors.New("bdd used: duplicate field")
)

// BDDUsedRepo exposes CRUD over the bdd_used_tables / bdd_used_fields
// pair plus a resolver used by the scoped gateway. All methods are
// safe to call concurrently; persistence is delegated to GORM.
type BDDUsedRepo struct {
	db *gorm.DB
}

// NewBDDUsedRepo wires the repository to a GORM handle. The handle is
// assumed to already have the BDD models migrated (see internal/db/mysql.go).
func NewBDDUsedRepo(g *gorm.DB) *BDDUsedRepo {
	return &BDDUsedRepo{db: g}
}

// isDuplicateKeyErr returns true when the underlying driver reports a
// uniqueness violation. We support the two backends we actually run
// against — MySQL in production (error 1062, matched via type assertion
// on *mysql.MySQLError) and SQLite in unit tests (error string
// "UNIQUE constraint failed").
func isDuplicateKeyErr(err error) bool {
	if err == nil {
		return false
	}
	var me *mysql.MySQLError
	if errors.As(err, &me) && me.Number == 1062 {
		return true
	}
	if strings.Contains(err.Error(), "UNIQUE constraint failed") {
		return true
	}
	return false
}

// ListTables returns the catalog of activated tables ordered by
// (database_id, table_name). When databaseID is non-nil the result is
// scoped to that database; when search is non-empty it is matched
// case-insensitively against table_name OR description.
func (r *BDDUsedRepo) ListTables(ctx context.Context, databaseID *int, search string) ([]db.BDDUsedTable, error) {
	q := r.db.WithContext(ctx).
		Preload("Fields", func(g *gorm.DB) *gorm.DB {
			return g.Order("field_name ASC")
		}).
		Order("database_id ASC, table_name ASC")

	if databaseID != nil {
		q = q.Where("database_id = ?", *databaseID)
	}
	if s := strings.TrimSpace(search); s != "" {
		needle := "%" + strings.ToLower(s) + "%"
		q = q.Where("LOWER(table_name) LIKE ? OR LOWER(description) LIKE ?", needle, needle)
	}

	var rows []db.BDDUsedTable
	if err := q.Find(&rows).Error; err != nil {
		return nil, err
	}
	return rows, nil
}

// GetTable returns a single table with its fields preloaded.
func (r *BDDUsedRepo) GetTable(ctx context.Context, id string) (*db.BDDUsedTable, error) {
	var out db.BDDUsedTable
	err := r.db.WithContext(ctx).
		Preload("Fields", func(g *gorm.DB) *gorm.DB {
			return g.Order("field_name ASC")
		}).
		First(&out, "id = ?", id).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrBDDNotFound
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// CreateTable inserts a table and its fields atomically. UUIDs are
// generated for any empty IDs. Each field's UsedTableID is overwritten
// with the parent table ID. A unique-index violation on
// (database_id, table_name) is surfaced as ErrBDDDuplicateTable.
func (r *BDDUsedRepo) CreateTable(ctx context.Context, table *db.BDDUsedTable, fields []db.BDDUsedField) (*db.BDDUsedTable, error) {
	if table == nil {
		return nil, errors.New("bdd used: nil table")
	}
	if table.ID == "" {
		table.ID = uuid.NewString()
	}

	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(table).Error; err != nil {
			if isDuplicateKeyErr(err) {
				return ErrBDDDuplicateTable
			}
			return err
		}
		for i := range fields {
			if fields[i].ID == "" {
				fields[i].ID = uuid.NewString()
			}
			fields[i].UsedTableID = table.ID
			if err := tx.Create(&fields[i]).Error; err != nil {
				if isDuplicateKeyErr(err) {
					return ErrBDDDuplicateField
				}
				return err
			}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}

	var out db.BDDUsedTable
	if err := r.db.WithContext(ctx).
		Preload("Fields", func(g *gorm.DB) *gorm.DB {
			return g.Order("field_name ASC")
		}).
		First(&out, "id = ?", table.ID).Error; err != nil {
		return nil, err
	}
	return &out, nil
}

// UpdateTableDescription rewrites only the description column. Returns
// ErrBDDNotFound when no row matches. Uses Updates(map) instead of
// Update("col", val) so an empty string actually clears the column —
// GORM v1's Update skips zero-values silently in some versions.
func (r *BDDUsedRepo) UpdateTableDescription(ctx context.Context, id, description string) error {
	res := r.db.WithContext(ctx).
		Model(&db.BDDUsedTable{}).
		Where("id = ?", id).
		Updates(map[string]interface{}{"description": description})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrBDDNotFound
	}
	return nil
}

// DeleteTable removes a table and its scope-token / OAuth2 join rows.
//
// The DB-level FK cascade already drops bdd_used_fields rows, but the
// gateway models (db.ScopeTokenBDDTable, db.OAuth2ClientBDDTable) do not
// declare a GORM FK constraint pointing back at bdd_used_tables.id, so
// MySQL does not enforce a cascade there. We clear those join tables
// inside a single transaction with the parent delete to keep token /
// client filter sets honest after a registry row is removed.
func (r *BDDUsedRepo) DeleteTable(ctx context.Context, id string) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("used_table_id = ?", id).Delete(&db.ScopeTokenBDDTable{}).Error; err != nil {
			return err
		}
		if err := tx.Where("used_table_id = ?", id).Delete(&db.OAuth2ClientBDDTable{}).Error; err != nil {
			return err
		}
		res := tx.Delete(&db.BDDUsedTable{}, "id = ?", id)
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return ErrBDDNotFound
		}
		return nil
	})
}

// AddField appends a single field to an existing table. ErrBDDNotFound
// when the parent table is absent; ErrBDDDuplicateField on a
// (used_table_id, field_name) collision.
func (r *BDDUsedRepo) AddField(ctx context.Context, usedTableID string, field *db.BDDUsedField) (*db.BDDUsedField, error) {
	if field == nil {
		return nil, errors.New("bdd used: nil field")
	}

	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var parent db.BDDUsedTable
		if err := tx.First(&parent, "id = ?", usedTableID).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrBDDNotFound
			}
			return err
		}
		if field.ID == "" {
			field.ID = uuid.NewString()
		}
		field.UsedTableID = usedTableID
		if err := tx.Create(field).Error; err != nil {
			if isDuplicateKeyErr(err) {
				return ErrBDDDuplicateField
			}
			return err
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return field, nil
}

// UpdateFieldDescription rewrites the description for a single field.
// Uses Updates(map) instead of Update("col", val) so an empty string
// actually clears the column — GORM v1's Update skips zero-values
// silently in some versions.
func (r *BDDUsedRepo) UpdateFieldDescription(ctx context.Context, fieldID, description string) error {
	res := r.db.WithContext(ctx).
		Model(&db.BDDUsedField{}).
		Where("id = ?", fieldID).
		Updates(map[string]interface{}{"description": description})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrBDDNotFound
	}
	return nil
}

// DeleteField removes a single field by ID.
func (r *BDDUsedRepo) DeleteField(ctx context.Context, fieldID string) error {
	res := r.db.WithContext(ctx).Delete(&db.BDDUsedField{}, "id = ?", fieldID)
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrBDDNotFound
	}
	return nil
}

// ResolveByDBAndName fetches a table by its (database_id, table_name)
// pair. Used by the scoped gateway in Task 4 to translate the
// catalog-side identifier into a registry row.
func (r *BDDUsedRepo) ResolveByDBAndName(ctx context.Context, databaseID int, tableName string) (*db.BDDUsedTable, error) {
	var out db.BDDUsedTable
	err := r.db.WithContext(ctx).
		Preload("Fields", func(g *gorm.DB) *gorm.DB {
			return g.Order("field_name ASC")
		}).
		Where("database_id = ? AND table_name = ?", databaseID, tableName).
		First(&out).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, ErrBDDNotFound
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}
