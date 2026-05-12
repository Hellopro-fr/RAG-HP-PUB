// Package db carries the read-side row shapes that match the columns
// queries.go selects. These are NOT the gateway's full GORM models —
// only the subset the resolver needs.
package db

// ServerRow is the narrow view of an mcp_servers row used by the resolver.
type ServerRow struct {
	ID          string
	URL         string
	AuthHeaders []byte // encrypted blob
	CreatedBy   string
}
