package api

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// TestCreateBDDUsedTableRequest_JSONShape verifies the wire contract:
// snake_case keys, including the inline fields[] payload. The frontend
// posts these exact keys, so any drift here is a breaking change.
func TestCreateBDDUsedTableRequest_JSONShape(t *testing.T) {
	raw := `{
        "database_id": 1,
        "table_name": "products",
        "description": "main product catalog",
        "upstream_table_id": 42,
        "fields": [
            {"field_name": "id", "description": "primary key", "upstream_field_id": 100},
            {"field_name": "name"}
        ]
    }`

	var req CreateBDDUsedTableRequest
	if err := json.Unmarshal([]byte(raw), &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.DatabaseID != 1 {
		t.Errorf("DatabaseID=%d want=1", req.DatabaseID)
	}
	if req.TableName != "products" {
		t.Errorf("TableName=%q want=products", req.TableName)
	}
	if req.UpstreamTableID != 42 {
		t.Errorf("UpstreamTableID=%d want=42", req.UpstreamTableID)
	}
	if len(req.Fields) != 2 {
		t.Fatalf("len(Fields)=%d want=2", len(req.Fields))
	}
	if req.Fields[0].FieldName != "id" || req.Fields[0].UpstreamFieldID != 100 {
		t.Errorf("Fields[0]=%+v", req.Fields[0])
	}
	if req.Fields[1].FieldName != "name" || req.Fields[1].UpstreamFieldID != 0 {
		t.Errorf("Fields[1]=%+v", req.Fields[1])
	}

	// Round-trip: marshalling must keep snake_case keys.
	out, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	for _, key := range []string{`"database_id"`, `"table_name"`, `"upstream_table_id"`, `"fields"`, `"field_name"`} {
		if !strings.Contains(string(out), key) {
			t.Errorf("output %q missing key %s", string(out), key)
		}
	}
	// Reject the Go field names — the wire contract is snake_case only.
	// (Don't search for `"name"` directly: one of the inline fields legitimately
	// has field_name="name" so the literal token appears in the field VALUE.)
	for _, badKey := range []string{`"DatabaseID"`, `"TableName"`, `"FieldName"`} {
		if strings.Contains(string(out), badKey) {
			t.Errorf("output %q contains bad key %s", string(out), badKey)
		}
	}
}

// TestUpdateBDDUsedTableRequest_JSONShape — only `description` is on the wire.
func TestUpdateBDDUsedTableRequest_JSONShape(t *testing.T) {
	var req UpdateBDDUsedTableRequest
	if err := json.Unmarshal([]byte(`{"description":"new"}`), &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.Description == nil || *req.Description != "new" {
		t.Errorf("Description=%v want=new", req.Description)
	}
	out, _ := json.Marshal(req)
	if !strings.Contains(string(out), `"description"`) {
		t.Errorf("output missing description: %s", out)
	}
}

// TestAddBDDUsedFieldRequest_JSONShape — verifies the field-level POST body.
func TestAddBDDUsedFieldRequest_JSONShape(t *testing.T) {
	raw := `{"field_name":"price","description":"unit price","upstream_field_id":7}`
	var req AddBDDUsedFieldRequest
	if err := json.Unmarshal([]byte(raw), &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.FieldName != "price" || req.UpstreamFieldID != 7 || req.Description != "unit price" {
		t.Errorf("req=%+v", req)
	}
	out, _ := json.Marshal(req)
	for _, key := range []string{`"field_name"`, `"description"`, `"upstream_field_id"`} {
		if !strings.Contains(string(out), key) {
			t.Errorf("output %q missing key %s", string(out), key)
		}
	}
}

// TestUpdateBDDUsedFieldRequest_JSONShape — only `description` is on the wire.
func TestUpdateBDDUsedFieldRequest_JSONShape(t *testing.T) {
	var req UpdateBDDUsedFieldRequest
	if err := json.Unmarshal([]byte(`{"description":"updated"}`), &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.Description != "updated" {
		t.Errorf("Description=%q want=updated", req.Description)
	}
}

// TestToBDDUsedTableDTO_MapsModelToWire verifies the GORM-to-DTO mapping
// surfaces the struct field `Name` as the JSON key `table_name`.
// This is the riskiest mapping in the package because the column name
// differs from the Go struct field name.
func TestToBDDUsedTableDTO_MapsModelToWire(t *testing.T) {
	now := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	model := db.BDDUsedTable{
		ID:              "t-1",
		DatabaseID:      5,
		Name:            "products",
		UpstreamTableID: 99,
		Description:     "main",
		CreatedBy:       "alice@hellopro.fr",
		CreatedAt:       now,
		UpdatedAt:       now,
		Fields: []db.BDDUsedField{
			{
				ID:              "f-1",
				UsedTableID:     "t-1",
				FieldName:       "id",
				UpstreamFieldID: 11,
				Description:     "pk",
				CreatedAt:       now,
				UpdatedAt:       now,
			},
		},
	}
	dto := toBDDUsedTableDTO(model)
	if dto.TableName != "products" {
		t.Errorf("TableName=%q want=products (model.Name -> dto.TableName)", dto.TableName)
	}
	if dto.DatabaseID != 5 {
		t.Errorf("DatabaseID=%d want=5", dto.DatabaseID)
	}
	if dto.CreatedBy != "alice@hellopro.fr" {
		t.Errorf("CreatedBy=%q", dto.CreatedBy)
	}
	if len(dto.Fields) != 1 {
		t.Fatalf("len(Fields)=%d want=1", len(dto.Fields))
	}
	if dto.Fields[0].FieldName != "id" || dto.Fields[0].UpstreamFieldID != 11 {
		t.Errorf("Field[0]=%+v", dto.Fields[0])
	}

	out, err := json.Marshal(dto)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(out), `"table_name":"products"`) {
		t.Errorf("output missing table_name key: %s", out)
	}
	if strings.Contains(string(out), `"name"`) {
		t.Errorf("output leaked Name field as `name`: %s", out)
	}
}

// TestToBDDUsedTableDTO_EmptyFieldsIsArrayNotNull guards the JSON contract
// the frontend relies on: a table with no fields must serialise as
// `"fields":[]`, never `"fields":null`.
func TestToBDDUsedTableDTO_EmptyFieldsIsArrayNotNull(t *testing.T) {
	model := db.BDDUsedTable{ID: "t-1", DatabaseID: 1, Name: "x"}
	dto := toBDDUsedTableDTO(model)
	if dto.Fields == nil {
		t.Fatal("Fields is nil; expected empty slice")
	}
	out, _ := json.Marshal(dto)
	if !strings.Contains(string(out), `"fields":[]`) {
		t.Errorf("expected fields:[] in %s", out)
	}
}

// TestToBDDFieldDTO_MapsAllColumns verifies the field-level mapping has
// no surprises (FieldName already matches both struct and column).
func TestToBDDFieldDTO_MapsAllColumns(t *testing.T) {
	now := time.Date(2026, 4, 27, 10, 0, 0, 0, time.UTC)
	f := db.BDDUsedField{
		ID:              "f-1",
		UsedTableID:     "t-1",
		FieldName:       "name",
		UpstreamFieldID: 7,
		Description:     "label",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	dto := toBDDFieldDTO(f)
	if dto.ID != "f-1" || dto.UsedTableID != "t-1" || dto.FieldName != "name" {
		t.Errorf("dto=%+v", dto)
	}
	if dto.UpstreamFieldID != 7 || dto.Description != "label" {
		t.Errorf("dto=%+v", dto)
	}
	if !dto.CreatedAt.Equal(now) || !dto.UpdatedAt.Equal(now) {
		t.Errorf("timestamps mismatch: %+v", dto)
	}
}
