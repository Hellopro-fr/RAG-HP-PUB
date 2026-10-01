// Package bddcatalog provides a read-only HTTP client for the upstream
// Hellopro BDD catalog service. It exposes the small set of GETs the
// gateway needs to populate the "Hellopro BDD tables" admin onglet with
// the list of available databases, tables, and fields. All write paths
// (creating "used tables" and "used fields") live in the gateway's own
// repository — the upstream catalog is treated as the source of truth
// for schema metadata only.
package bddcatalog

// Database is the lightweight database descriptor returned by the catalog.
type Database struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

// Table is a single table descriptor. If the upstream payload grows extra
// fields, re-introduce capture via a custom UnmarshalJSON.
type Table struct {
	ID          int    `json:"id"`
	DatabaseID  int    `json:"database_id"`
	TableName   string `json:"table_name"`
	Description string `json:"description,omitempty"`
	FieldCount  int    `json:"field_count,omitempty"`
}

// Field describes one column of a table.
type Field struct {
	ID          int    `json:"id"`
	TableID     int    `json:"table_id"`
	FieldName   string `json:"field_name"`
	FieldType   string `json:"field_type,omitempty"`
	IsNullable  bool   `json:"is_nullable,omitempty"`
	Description string `json:"description,omitempty"`
}
