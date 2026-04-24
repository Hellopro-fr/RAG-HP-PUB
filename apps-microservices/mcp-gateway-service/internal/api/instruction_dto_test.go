package api

import (
	"testing"
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
)

func TestToLLMInstructionResponse(t *testing.T) {
	now := time.Date(2026, 4, 23, 12, 0, 0, 0, time.UTC)
	ins := &db.LLMInstruction{
		ID:          "abc",
		Title:       "Page title",
		Description: "admin note",
		CreatedBy:   "user@example.com",
		CreatedAt:   now,
		UpdatedAt:   now,
		Rows: []db.LLMInstructionRow{
			{
				ID:           "r1",
				Title:        "First",
				Body:         "body1",
				DisplayOrder: 0,
				Servers: []db.LLMInstructionRowServer{
					{RowID: "r1", ServerID: "s1"},
					{RowID: "r1", ServerID: "s2"},
				},
			},
			{
				ID:           "r2",
				Body:         "body2",
				DisplayOrder: 1,
			},
		},
	}
	got := toLLMInstructionResponse(ins)
	if got.Title != "Page title" || got.Description != "admin note" {
		t.Errorf("page fields mismatch: %+v", got)
	}
	if len(got.Rows) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(got.Rows))
	}
	if got.Rows[0].Title != "First" || got.Rows[0].Body != "body1" {
		t.Errorf("row[0] fields mismatch: %+v", got.Rows[0])
	}
	if len(got.Rows[0].ServerIDs) != 2 {
		t.Errorf("row[0] server_ids should have 2 entries, got %+v", got.Rows[0].ServerIDs)
	}
	if got.Rows[1].ServerIDs == nil {
		t.Errorf("row[1] server_ids should be empty slice, not nil, for stable JSON output")
	}
	if got.Rows[1].DisplayOrder != 1 {
		t.Errorf("display_order should round-trip: %+v", got.Rows[1])
	}
}

func TestToLLMInstructionResponse_EmptyRows(t *testing.T) {
	ins := &db.LLMInstruction{ID: "id", Title: "t"}
	got := toLLMInstructionResponse(ins)
	if got.Rows == nil {
		t.Error("rows should be non-nil empty slice")
	}
	if len(got.Rows) != 0 {
		t.Errorf("expected empty slice, got %v", got.Rows)
	}
}
