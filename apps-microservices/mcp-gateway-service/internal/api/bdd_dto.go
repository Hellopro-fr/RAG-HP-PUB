package api

import (
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// BDDFieldDTO is the JSON-friendly view of a BDDUsedField row.
type BDDFieldDTO struct {
	ID              string    `json:"id"`
	UsedTableID     string    `json:"used_table_id"`
	FieldName       string    `json:"field_name"`
	Description     string    `json:"description"`
	UpstreamFieldID int       `json:"upstream_field_id,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

// BDDUsedTableDTO is the JSON-friendly view of a BDDUsedTable row plus
// its preloaded fields. Note: the DB Go field is `Name` but we surface it
// as `table_name` to match the upstream catalog naming and the SQL column.
type BDDUsedTableDTO struct {
	ID              string        `json:"id"`
	DatabaseID      int           `json:"database_id"`
	TableName       string        `json:"table_name"`
	Description     string        `json:"description"`
	UpstreamTableID int           `json:"upstream_table_id,omitempty"`
	CreatedBy       string        `json:"created_by,omitempty"`
	CreatedAt       time.Time     `json:"created_at"`
	UpdatedAt       time.Time     `json:"updated_at"`
	Fields          []BDDFieldDTO `json:"fields"`
}

// CreateBDDUsedTableRequest is the payload for POST /api/v1/bdd/used/tables.
type CreateBDDUsedTableRequest struct {
	DatabaseID      int                        `json:"database_id"`
	TableName       string                     `json:"table_name"`
	Description     string                     `json:"description,omitempty"`
	UpstreamTableID int                        `json:"upstream_table_id,omitempty"`
	Fields          []CreateBDDUsedFieldInline `json:"fields"`
}

// CreateBDDUsedFieldInline is one field carried in a CreateBDDUsedTableRequest.
type CreateBDDUsedFieldInline struct {
	FieldName       string `json:"field_name"`
	Description     string `json:"description,omitempty"`
	UpstreamFieldID int    `json:"upstream_field_id,omitempty"`
}

// UpdateBDDUsedTableRequest is the payload for PATCH /api/v1/bdd/used/tables/{id}.
type UpdateBDDUsedTableRequest struct {
	Description string `json:"description"`
}

// UpdateBDDUsedFieldRequest is the payload for PATCH /api/v1/bdd/used/tables/{id}/fields/{field_id}.
type UpdateBDDUsedFieldRequest struct {
	Description string `json:"description"`
}

// AddBDDUsedFieldRequest is the payload for POST /api/v1/bdd/used/tables/{id}/fields.
type AddBDDUsedFieldRequest struct {
	FieldName       string `json:"field_name"`
	Description     string `json:"description,omitempty"`
	UpstreamFieldID int    `json:"upstream_field_id,omitempty"`
}

// BDDUsedListResponse is the paginated envelope for
// GET /api/v1/bdd/used/tables. The previous shape was a bare
// {"tables":[...]}; consumers MUST migrate to read total/page/limit
// when pagination matters (the array still keys on "tables").
type BDDUsedListResponse struct {
	Tables []BDDUsedTableDTO `json:"tables"`
	Total  int64             `json:"total"`
	Page   int               `json:"page"`
	Limit  int               `json:"limit"`
}

// BulkCreateBDDUsedTablesRequest is the payload for
// POST /api/v1/bdd/used/tables/bulk. DatabaseID is shared across all
// items — bulk creation is per-database. Items is capped at 50 by the
// handler.
type BulkCreateBDDUsedTablesRequest struct {
	DatabaseID int                          `json:"database_id"`
	Items      []BulkCreateBDDUsedTableItem `json:"items"`
}

// BulkCreateBDDUsedTableItem is one entry in a bulk-create batch.
// Mirrors the shape of CreateBDDUsedTableRequest minus the database_id
// (which lives on the envelope) and the inline fields list (bulk
// create persists tables only; per-table fields are added afterwards
// via the existing /fields endpoint).
type BulkCreateBDDUsedTableItem struct {
	TableName       string `json:"table_name"`
	Description     string `json:"description,omitempty"`
	UpstreamTableID int    `json:"upstream_table_id,omitempty"`
}

// BulkCreateBDDUsedTableError carries the per-item failure surfaced in
// the bulk-create response body. Empty error string means success and
// the row appears in Created instead.
type BulkCreateBDDUsedTableError struct {
	TableName string `json:"table_name"`
	Error     string `json:"error"`
}

// BulkCreateBDDUsedTablesResponse summarizes a bulk-create call.
// Status code semantics: 201 = all items created, 200 = mixed
// success/failure, 400 = every item failed.
type BulkCreateBDDUsedTablesResponse struct {
	Created []BDDUsedTableDTO             `json:"created"`
	Errors  []BulkCreateBDDUsedTableError `json:"errors,omitempty"`
}

// BDDExportPayload is the registry-level export envelope returned by
// GET /api/v1/bdd/used/tables/export and consumed by the matching
// import endpoint. Version is a literal 1; bumping it is reserved for
// schema-incompatible changes in future migrations.
type BDDExportPayload struct {
	Version    int                `json:"version"`
	ExportedAt time.Time          `json:"exported_at"`
	Tables     []BDDExportedTable `json:"tables"`
}

// BDDExportedTable is one row in the export payload. Fields are nested
// for human-readable round-tripping (no separate "fields" sheet).
type BDDExportedTable struct {
	DatabaseID      int                `json:"database_id"`
	TableName       string             `json:"table_name"`
	Description     string             `json:"description"`
	UpstreamTableID int                `json:"upstream_table_id,omitempty"`
	Fields          []BDDExportedField `json:"fields"`
}

// BDDExportedField is one field row inside a BDDExportedTable. IDs and
// timestamps are intentionally omitted — they regenerate on import.
type BDDExportedField struct {
	FieldName       string `json:"field_name"`
	Description     string `json:"description"`
	UpstreamFieldID int    `json:"upstream_field_id,omitempty"`
}

// BDDImportResponse is the per-row outcome of POST
// /api/v1/bdd/used/tables/import. Inserted + Updated count successful
// upserts; Errors describes catastrophic per-row failures that didn't
// fit either category.
type BDDImportResponse struct {
	Inserted int              `json:"inserted"`
	Updated  int              `json:"updated"`
	Errors   []BDDImportError `json:"errors,omitempty"`
}

// BDDImportError pinpoints a failed import row by (database_id, name).
type BDDImportError struct {
	DatabaseID int    `json:"database_id"`
	TableName  string `json:"table_name"`
	Error      string `json:"error"`
}

// toBDDFieldDTO converts a db.BDDUsedField into its JSON-friendly view.
func toBDDFieldDTO(f db.BDDUsedField) BDDFieldDTO {
	return BDDFieldDTO{
		ID:              f.ID,
		UsedTableID:     f.UsedTableID,
		FieldName:       f.FieldName,
		Description:     f.Description,
		UpstreamFieldID: f.UpstreamFieldID,
		CreatedAt:       f.CreatedAt,
		UpdatedAt:       f.UpdatedAt,
	}
}

// toBDDUsedTableDTO converts a db.BDDUsedTable (with preloaded fields)
// into the JSON-friendly view returned by the registry handlers.
func toBDDUsedTableDTO(t db.BDDUsedTable) BDDUsedTableDTO {
	fields := make([]BDDFieldDTO, 0, len(t.Fields))
	for _, f := range t.Fields {
		fields = append(fields, toBDDFieldDTO(f))
	}
	return BDDUsedTableDTO{
		ID:              t.ID,
		DatabaseID:      t.DatabaseID,
		TableName:       t.Name,
		Description:     t.Description,
		UpstreamTableID: t.UpstreamTableID,
		CreatedBy:       t.CreatedBy,
		CreatedAt:       t.CreatedAt,
		UpdatedAt:       t.UpdatedAt,
		Fields:          fields,
	}
}
