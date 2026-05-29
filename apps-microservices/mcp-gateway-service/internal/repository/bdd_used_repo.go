package repository

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"time"

	"github.com/go-sql-driver/mysql"
	"github.com/google/uuid"
	"gorm.io/gorm"

	"mcp-gateway/internal/db"
)

// Sentinel errors surfaced by BDDUsedRepo. Callers should rely on
// errors.Is to match these (driver-specific causes are wrapped).
var (
	ErrBDDNotFound       = errors.New("bdd used: not found")
	ErrBDDDuplicateTable = errors.New("bdd used: duplicate table")
	ErrBDDDuplicateField = errors.New("bdd used: duplicate field")
)

// ListTablesOptions carries the optional filters and the pagination
// window for ListTables. A nil DatabaseID returns rows across every
// database. Limit must be positive (callers cap at the API layer);
// Offset is zero-based.
type ListTablesOptions struct {
	DatabaseID *int
	Search     string
	Limit      int
	Offset     int
}

// BulkCreateItem is a single row submitted to BulkCreate. Empty fields
// slice = no fields registered for that table. Validation of names is
// the caller's job — the repo simply persists and surfaces duplicate
// errors.
type BulkCreateItem struct {
	TableName       string
	Description     string
	UpstreamTableID int
}

// BulkCreateResult mirrors a single input row's outcome. When Err is
// non-nil the row was not persisted; otherwise Table holds the freshly
// inserted record (with its generated ID and timestamps).
type BulkCreateResult struct {
	TableName string
	Table     *db.BDDUsedTable
	Err       error
}

// ImportError is one row's outcome from a failed Import upsert. It is
// returned alongside aggregate counts so the API layer can report a
// per-row diagnostic without aborting the whole import.
type ImportError struct {
	DatabaseID int
	TableName  string
	Err        error
}

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

// applyListTablesFilters appends the WHERE predicates shared by the
// paginated Find and the matching Count. Centralising the predicate
// builder keeps the two queries from drifting.
func applyListTablesFilters(q *gorm.DB, opts ListTablesOptions) *gorm.DB {
	if opts.DatabaseID != nil {
		q = q.Where("database_id = ?", *opts.DatabaseID)
	}
	if s := strings.TrimSpace(opts.Search); s != "" {
		needle := "%" + strings.ToLower(s) + "%"
		q = q.Where("LOWER(table_name) LIKE ? OR LOWER(description) LIKE ?", needle, needle)
	}
	return q
}

// ListTables returns a paginated slice of activated tables alongside the
// total row count matching the same filters. Ordering is
// (created_at DESC, table_name ASC) so the most recent registrations
// surface first while still being deterministic when timestamps tie.
//
// A nil opts.DatabaseID returns rows across every database; a non-empty
// opts.Search is matched case-insensitively against table_name OR
// description. Limit/Offset come straight from the API layer (already
// validated and capped there).
func (r *BDDUsedRepo) ListTables(ctx context.Context, opts ListTablesOptions) ([]db.BDDUsedTable, int64, error) {
	base := r.db.WithContext(ctx).Model(&db.BDDUsedTable{})
	base = applyListTablesFilters(base, opts)

	var total int64
	if err := base.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	q := r.db.WithContext(ctx).
		Preload("Fields", func(g *gorm.DB) *gorm.DB {
			return g.Order("field_name ASC")
		}).
		Order("created_at DESC, table_name ASC")
	q = applyListTablesFilters(q, opts)
	if opts.Limit > 0 {
		q = q.Limit(opts.Limit)
	}
	if opts.Offset > 0 {
		q = q.Offset(opts.Offset)
	}

	var rows []db.BDDUsedTable
	if err := q.Find(&rows).Error; err != nil {
		return nil, 0, err
	}
	return rows, total, nil
}

// ListAll returns the complete registry (all databases, all rows) with
// fields preloaded. Used by the export endpoint, which must capture
// every row regardless of pagination. Ordering matches ListTables.
func (r *BDDUsedRepo) ListAll(ctx context.Context) ([]db.BDDUsedTable, error) {
	var rows []db.BDDUsedTable
	err := r.db.WithContext(ctx).
		Preload("Fields", func(g *gorm.DB) *gorm.DB {
			return g.Order("field_name ASC")
		}).
		Order("created_at DESC, table_name ASC").
		Find(&rows).Error
	if err != nil {
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

// UpdateTableMetadata accepts a sparse column map (description, rows,
// primary_key, default_order_by, relations, notes) and applies it to the
// row in one statement. Empty map is a no-op (returns nil). Caller is
// responsible for whitelisting allowed keys.
func (r *BDDUsedRepo) UpdateTableMetadata(ctx context.Context, id string, fields map[string]interface{}) error {
	if len(fields) == 0 {
		return nil
	}
	res := r.db.WithContext(ctx).
		Model(&db.BDDUsedTable{}).
		Where("id = ?", id).
		Updates(fields)
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrBDDNotFound
	}
	return nil
}

// BulkUpdate applies the same set of updates to every table whose id is in
// `ids`. Allowed columns: database_id, is_active. Returns the number of
// rows that matched (0 when ids is empty or nothing matched).
func (r *BDDUsedRepo) BulkUpdate(ctx context.Context, ids []string, updates map[string]interface{}) (int64, error) {
	if len(ids) == 0 || len(updates) == 0 {
		return 0, nil
	}
	res := r.db.WithContext(ctx).
		Model(&db.BDDUsedTable{}).
		Where("id IN ?", ids).
		Updates(updates)
	return res.RowsAffected, res.Error
}

// BulkDelete removes a set of tables and their scope-token / OAuth2-client
// join rows in one transaction. Mirrors DeleteTable's cascade semantics
// for batches. Returns the number of registry rows actually deleted.
func (r *BDDUsedRepo) BulkDelete(ctx context.Context, ids []string) (int64, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	var deleted int64
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("used_table_id IN ?", ids).Delete(&db.ScopeTokenBDDTable{}).Error; err != nil {
			return err
		}
		if err := tx.Where("used_table_id IN ?", ids).Delete(&db.OAuth2ClientBDDTable{}).Error; err != nil {
			return err
		}
		res := tx.Where("id IN ?", ids).Delete(&db.BDDUsedTable{})
		if res.Error != nil {
			return res.Error
		}
		deleted = res.RowsAffected
		return nil
	})
	if err != nil {
		return 0, err
	}
	return deleted, nil
}

// LatestUpdatedAt returns the most recent updated_at across the registry
// (tables OR fields), falling back to zero time when the registry is
// empty. Used for the doc payload's _meta.last_updated.
func (r *BDDUsedRepo) LatestUpdatedAt(ctx context.Context) (time.Time, error) {
	var tableMax, fieldMax sql.NullTime
	if err := r.db.WithContext(ctx).
		Model(&db.BDDUsedTable{}).
		Select("MAX(updated_at)").
		Scan(&tableMax).Error; err != nil {
		return time.Time{}, err
	}
	if err := r.db.WithContext(ctx).
		Model(&db.BDDUsedField{}).
		Select("MAX(updated_at)").
		Scan(&fieldMax).Error; err != nil {
		return time.Time{}, err
	}
	out := time.Time{}
	if tableMax.Valid && tableMax.Time.After(out) {
		out = tableMax.Time
	}
	if fieldMax.Valid && fieldMax.Time.After(out) {
		out = fieldMax.Time
	}
	return out, nil
}

// GetMeta loads the singleton BDDMeta row. Returns a fresh zero-valued
// row when the table is empty (no error), so the caller never has to
// special-case "no meta yet".
func (r *BDDUsedRepo) GetMeta(ctx context.Context) (*db.BDDMeta, error) {
	var out db.BDDMeta
	err := r.db.WithContext(ctx).First(&out, "id = ?", 1).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return &db.BDDMeta{ID: 1}, nil
	}
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// UpsertMeta writes the singleton BDDMeta row, creating it when missing.
// updatedBy is stamped onto every write.
func (r *BDDUsedRepo) UpsertMeta(ctx context.Context, description, usage, updatedBy string) (*db.BDDMeta, error) {
	row := db.BDDMeta{
		ID:          1,
		Description: description,
		Usage:       usage,
		UpdatedBy:   updatedBy,
	}
	err := r.db.WithContext(ctx).Save(&row).Error
	if err != nil {
		return nil, err
	}
	return &row, nil
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

// FieldTypeSync is the desired state for one field during a catalog sync.
// Type is the (already normalized) short type written to field_type.
// FullDef, when non-empty, is the verbose upstream definition (e.g. the
// full enum(...) list) used to seed the description ONLY when the field
// has no curated description yet — never clobbering admin-entered text.
type FieldTypeSync struct {
	Type    string
	FullDef string
}

// SyncFieldTypes reconciles field_type (and optionally a seed description)
// for the table's fields whose name appears in byName. For each match it
// updates field_type when the normalized type differs, and sets the
// description to FullDef only when the stored description is empty. Names
// not registered for the table are ignored. Returns the number of field
// rows actually changed. A table with no matching changes yields (0, nil).
func (r *BDDUsedRepo) SyncFieldTypes(ctx context.Context, usedTableID string, byName map[string]FieldTypeSync) (int, error) {
	if len(byName) == 0 {
		return 0, nil
	}
	updated := 0
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var fields []db.BDDUsedField
		if err := tx.Where("used_table_id = ?", usedTableID).Find(&fields).Error; err != nil {
			return err
		}
		for _, f := range fields {
			want, ok := byName[f.FieldName]
			if !ok {
				continue
			}
			updates := map[string]interface{}{}
			if want.Type != "" && want.Type != f.FieldType {
				updates["field_type"] = want.Type
			}
			if want.FullDef != "" && strings.TrimSpace(f.Description) == "" {
				updates["description"] = want.FullDef
			}
			if len(updates) == 0 {
				continue
			}
			res := tx.Model(&db.BDDUsedField{}).
				Where("id = ?", f.ID).
				Updates(updates)
			if res.Error != nil {
				return res.Error
			}
			updated += int(res.RowsAffected)
		}
		return nil
	})
	if err != nil {
		return 0, err
	}
	return updated, nil
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

// BulkCreate inserts every item in a single transaction, returning a
// per-item result so the caller can build a "created + errors" mixed
// response. Item-level failures (duplicate name, generic insert error)
// are recorded into the result slice and do NOT abort the transaction
// — each row is wrapped in a SAVEPOINT so a single duplicate doesn't
// poison the rest. createdBy is stamped onto every newly-inserted row.
func (r *BDDUsedRepo) BulkCreate(ctx context.Context, databaseID int, items []BulkCreateItem, createdBy string) ([]BulkCreateResult, error) {
	results := make([]BulkCreateResult, len(items))
	if len(items) == 0 {
		return results, nil
	}

	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for i, it := range items {
			results[i].TableName = it.TableName
			row := db.BDDUsedTable{
				ID:              uuid.NewString(),
				DatabaseID:      databaseID,
				Name:            it.TableName,
				Description:     it.Description,
				UpstreamTableID: it.UpstreamTableID,
				CreatedBy:       createdBy,
			}
			// Wrap each insert in a SAVEPOINT so a duplicate-key error on one
			// row leaves the surrounding transaction usable for the rest.
			cerr := tx.Transaction(func(sp *gorm.DB) error {
				return sp.Create(&row).Error
			})
			if cerr != nil {
				if isDuplicateKeyErr(cerr) {
					results[i].Err = ErrBDDDuplicateTable
				} else {
					results[i].Err = cerr
				}
				continue
			}
			fresh := row
			results[i].Table = &fresh
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return results, nil
}

// Import upserts every row in payload by (database_id, table_name).
// Existing rows have their description and upstream_table_id refreshed
// and their fields atomically replaced (delete-then-insert). Missing
// rows are inserted with createdBy. Per-row failures are collected into
// errs and do NOT abort the transaction — each row is wrapped in a
// SAVEPOINT.
func (r *BDDUsedRepo) Import(ctx context.Context, payload []db.BDDUsedTable, createdBy string) (inserted, updated int, errs []ImportError, err error) {
	txErr := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, in := range payload {
			rowErr := tx.Transaction(func(sp *gorm.DB) error {
				var existing db.BDDUsedTable
				lookupErr := sp.Where("database_id = ? AND table_name = ?", in.DatabaseID, in.Name).
					First(&existing).Error
				switch {
				case errors.Is(lookupErr, gorm.ErrRecordNotFound):
					row := db.BDDUsedTable{
						ID:              uuid.NewString(),
						DatabaseID:      in.DatabaseID,
						Name:            in.Name,
						Description:     in.Description,
						UpstreamTableID: in.UpstreamTableID,
						Rows:            in.Rows,
						PrimaryKey:      in.PrimaryKey,
						DefaultOrderBy:  in.DefaultOrderBy,
						Relations:       in.Relations,
						Notes:           in.Notes,
						CreatedBy:       createdBy,
					}
					if cerr := sp.Create(&row).Error; cerr != nil {
						return cerr
					}
					for _, f := range in.Fields {
						field := db.BDDUsedField{
							ID:              uuid.NewString(),
							UsedTableID:     row.ID,
							FieldName:       f.FieldName,
							FieldType:       f.FieldType,
							Description:     f.Description,
							UpstreamFieldID: f.UpstreamFieldID,
						}
						if cerr := sp.Create(&field).Error; cerr != nil {
							return cerr
						}
					}
					inserted++
				case lookupErr != nil:
					return lookupErr
				default:
					updates := map[string]interface{}{
						"description":       in.Description,
						"upstream_table_id": in.UpstreamTableID,
						"rows":              in.Rows,
						"primary_key":       in.PrimaryKey,
						"default_order_by":  in.DefaultOrderBy,
						"relations":         in.Relations,
						"notes":             in.Notes,
					}
					if uerr := sp.Model(&db.BDDUsedTable{}).
						Where("id = ?", existing.ID).
						Updates(updates).Error; uerr != nil {
						return uerr
					}
					if derr := sp.Where("used_table_id = ?", existing.ID).
						Delete(&db.BDDUsedField{}).Error; derr != nil {
						return derr
					}
					for _, f := range in.Fields {
						field := db.BDDUsedField{
							ID:              uuid.NewString(),
							UsedTableID:     existing.ID,
							FieldName:       f.FieldName,
							FieldType:       f.FieldType,
							Description:     f.Description,
							UpstreamFieldID: f.UpstreamFieldID,
						}
						if cerr := sp.Create(&field).Error; cerr != nil {
							return cerr
						}
					}
					updated++
				}
				return nil
			})
			if rowErr != nil {
				errs = append(errs, ImportError{
					DatabaseID: in.DatabaseID,
					TableName:  in.Name,
					Err:        rowErr,
				})
			}
		}
		return nil
	})
	if txErr != nil {
		return 0, 0, nil, txErr
	}
	return inserted, updated, errs, nil
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
