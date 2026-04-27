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
