// Package db carries the read-side row shapes that match the columns
// queries.go selects. These are NOT the gateway's full GORM models —
// only the subset the resolver needs.
package db

// ImportRow is the narrow view of a zoho_imports row used by the resolver.
type ImportRow struct {
	ID          string
	URL         string
	AuthHeaders []byte
	CreatedBy   string
	IsAdmin     bool
}
