package repository

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// setupBDDTestDB creates an in-memory SQLite DB with a manual DDL that
// mirrors internal/db/models.go (BDDUsedTable + BDDUsedField). Manual
// DDL is required because the GORM `datetime(3)` MySQL-only tags are
// incompatible with SQLite.
//
// IMPORTANT: when models.go changes column/index/constraint shape,
// update this DDL in lockstep — there is no AutoMigrate parity check
// at test boot.
//
// Each call gets an isolated database via a unique DSN so tests don't
// share state.
func setupBDDTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	dsn := "file:" + t.Name() + "?mode=memory&cache=private&_foreign_keys=on"
	g, err := gorm.Open(sqlite.Open(dsn), &gorm.Config{
		Logger:               logger.Default.LogMode(logger.Silent),
		DisableAutomaticPing: true,
	})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := g.Exec("PRAGMA foreign_keys = ON").Error; err != nil {
		t.Fatalf("enable foreign keys: %v", err)
	}

	// SQLite-friendly DDL — TEXT timestamps avoid the datetime(3) scan
	// failure produced by AutoMigrate against the MySQL-tagged models.
	stmts := []string{
		`CREATE TABLE bdd_used_tables (
			id TEXT PRIMARY KEY,
			database_id INTEGER NOT NULL,
			table_name TEXT NOT NULL,
			upstream_table_id INTEGER,
			description TEXT,
			created_by TEXT NOT NULL DEFAULT '',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			UNIQUE (database_id, table_name)
		)`,
		`CREATE INDEX idx_bdd_used_tables_database_id ON bdd_used_tables(database_id)`,
		`CREATE INDEX idx_bdd_used_tables_upstream_table_id ON bdd_used_tables(upstream_table_id)`,
		`CREATE TABLE bdd_used_fields (
			id TEXT PRIMARY KEY,
			used_table_id TEXT NOT NULL,
			field_name TEXT NOT NULL,
			upstream_field_id INTEGER,
			description TEXT,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			UNIQUE (used_table_id, field_name),
			FOREIGN KEY (used_table_id) REFERENCES bdd_used_tables(id) ON DELETE CASCADE
		)`,
		`CREATE INDEX idx_bdd_used_fields_used_table_id ON bdd_used_fields(used_table_id)`,
		`CREATE INDEX idx_bdd_used_fields_upstream_field_id ON bdd_used_fields(upstream_field_id)`,
	}
	for _, s := range stmts {
		if err := g.Exec(s).Error; err != nil {
			t.Fatalf("ddl: %v\n%s", err, s)
		}
	}

	t.Cleanup(func() {
		sqlDB, err := g.DB()
		if err == nil {
			_ = sqlDB.Close()
		}
	})
	return g
}

func newTable(databaseID int, name string) *db.BDDUsedTable {
	return &db.BDDUsedTable{
		DatabaseID:  databaseID,
		Name:        name,
		Description: "desc-" + name,
		CreatedBy:   "tester@hellopro.fr",
	}
}

func TestCreateTable_GeneratesID(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	tbl := newTable(1, "products")
	out, err := repo.CreateTable(context.Background(), tbl, nil)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	if out.ID == "" {
		t.Fatal("expected non-empty ID")
	}
	if _, err := uuid.Parse(out.ID); err != nil {
		t.Fatalf("expected ID to be a UUID, got %q: %v", out.ID, err)
	}
}

func TestCreateTable_WithFields_AtomicInsert(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	tbl := newTable(1, "products")
	fields := []db.BDDUsedField{
		{FieldName: "zeta", Description: "last"},
		{FieldName: "alpha", Description: "first"},
		{FieldName: "mid", Description: "middle"},
	}
	out, err := repo.CreateTable(context.Background(), tbl, fields)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	if len(out.Fields) != 3 {
		t.Fatalf("expected 3 fields, got %d", len(out.Fields))
	}
	wantOrder := []string{"alpha", "mid", "zeta"}
	for i, f := range out.Fields {
		if f.FieldName != wantOrder[i] {
			t.Errorf("field[%d]: want %q, got %q", i, wantOrder[i], f.FieldName)
		}
		if f.UsedTableID != out.ID {
			t.Errorf("field[%d].UsedTableID = %q, want %q", i, f.UsedTableID, out.ID)
		}
		if f.ID == "" {
			t.Errorf("field[%d].ID is empty", i)
		}
	}
}

func TestCreateTable_DuplicateName(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil); err != nil {
		t.Fatalf("first insert: %v", err)
	}
	_, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil)
	if !errors.Is(err, ErrBDDDuplicateTable) {
		t.Fatalf("expected ErrBDDDuplicateTable, got %v", err)
	}
}

func TestGetTable_NotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	_, err := repo.GetTable(context.Background(), uuid.NewString())
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}

func TestGetTable_Success(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(2, "orders"), []db.BDDUsedField{
		{FieldName: "id"},
		{FieldName: "amount"},
	})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	got, err := repo.GetTable(context.Background(), created.ID)
	if err != nil {
		t.Fatalf("GetTable: %v", err)
	}
	if got.Name != "orders" || got.DatabaseID != 2 {
		t.Errorf("unexpected payload: %+v", got)
	}
	if len(got.Fields) != 2 {
		t.Errorf("expected 2 fields, got %d", len(got.Fields))
	}
}

func TestListTables_FilterByDatabase(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil); err != nil {
		t.Fatalf("seed db1: %v", err)
	}
	if _, err := repo.CreateTable(context.Background(), newTable(5, "leads"), nil); err != nil {
		t.Fatalf("seed db5: %v", err)
	}
	if _, err := repo.CreateTable(context.Background(), newTable(5, "deals"), nil); err != nil {
		t.Fatalf("seed db5: %v", err)
	}

	one := 1
	got, err := repo.ListTables(context.Background(), &one, "")
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected 1 row for db1, got %d", len(got))
	}
	if got[0].Name != "products" {
		t.Errorf("unexpected row: %+v", got[0])
	}

	five := 5
	gotFive, err := repo.ListTables(context.Background(), &five, "")
	if err != nil {
		t.Fatalf("ListTables db5: %v", err)
	}
	if len(gotFive) != 2 {
		t.Fatalf("expected 2 rows for db5, got %d", len(gotFive))
	}
	// Ordered by table_name ASC: deals, leads
	if gotFive[0].Name != "deals" || gotFive[1].Name != "leads" {
		t.Errorf("unexpected order: %+v", gotFive)
	}
}

func TestListTables_Search(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.CreateTable(context.Background(), newTable(1, "orders"), nil); err != nil {
		t.Fatal(err)
	}
	tableWithDescription := newTable(1, "leads")
	tableWithDescription.Description = "Customer PRODUCT signals"
	if _, err := repo.CreateTable(context.Background(), tableWithDescription, nil); err != nil {
		t.Fatal(err)
	}

	// Case-insensitive search on table name + description.
	got, err := repo.ListTables(context.Background(), nil, "PrOd")
	if err != nil {
		t.Fatalf("ListTables search: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("expected 2 hits (products + leads via description), got %d", len(got))
	}
	names := map[string]bool{got[0].Name: true, got[1].Name: true}
	if !names["products"] || !names["leads"] {
		t.Errorf("unexpected hits: %+v", got)
	}
}

func TestUpdateTableDescription_NotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	err := repo.UpdateTableDescription(context.Background(), uuid.NewString(), "nope")
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}

func TestUpdateTableDescription_Success(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	if err := repo.UpdateTableDescription(context.Background(), created.ID, "fresh description"); err != nil {
		t.Fatalf("UpdateTableDescription: %v", err)
	}
	got, err := repo.GetTable(context.Background(), created.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Description != "fresh description" {
		t.Errorf("description not updated: %q", got.Description)
	}
}

// TestUpdateTableDescription_ToEmpty regression-guards against GORM's
// Update("col", val) silently skipping zero-values. We seed a non-empty
// description, then call UpdateTableDescription with "", and assert
// the column is actually cleared.
func TestUpdateTableDescription_ToEmpty(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	tbl := newTable(1, "products")
	tbl.Description = "initial description"
	created, err := repo.CreateTable(context.Background(), tbl, nil)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	if created.Description != "initial description" {
		t.Fatalf("seed description not persisted: %q", created.Description)
	}

	if err := repo.UpdateTableDescription(context.Background(), created.ID, ""); err != nil {
		t.Fatalf("UpdateTableDescription to empty: %v", err)
	}
	got, err := repo.GetTable(context.Background(), created.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Description != "" {
		t.Errorf("expected empty description, got %q", got.Description)
	}
}

func TestDeleteTable_CascadesFields(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), []db.BDDUsedField{
		{FieldName: "sku"},
		{FieldName: "price"},
	})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}

	if err := repo.DeleteTable(context.Background(), created.ID); err != nil {
		t.Fatalf("DeleteTable: %v", err)
	}

	// Verify the parent is gone.
	if _, err := repo.GetTable(context.Background(), created.ID); !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound after delete, got %v", err)
	}

	// Verify cascade — relies on PRAGMA foreign_keys=on. If sqlite cascade
	// turns out to be flaky in CI, re-think this assertion (per task brief).
	var leftover int64
	if err := g.Model(&db.BDDUsedField{}).Where("used_table_id = ?", created.ID).Count(&leftover).Error; err != nil {
		t.Fatalf("count leftover fields: %v", err)
	}
	if leftover != 0 {
		t.Errorf("expected 0 leftover fields, got %d", leftover)
	}
}

func TestDeleteTable_NotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	err := repo.DeleteTable(context.Background(), uuid.NewString())
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}

func TestAddField_ParentNotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	_, err := repo.AddField(context.Background(), uuid.NewString(), &db.BDDUsedField{FieldName: "x"})
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}

func TestAddField_Duplicate(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), []db.BDDUsedField{
		{FieldName: "sku"},
	})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	_, err = repo.AddField(context.Background(), created.ID, &db.BDDUsedField{FieldName: "sku"})
	if !errors.Is(err, ErrBDDDuplicateField) {
		t.Fatalf("expected ErrBDDDuplicateField, got %v", err)
	}
}

func TestAddField_Success(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	added, err := repo.AddField(context.Background(), created.ID, &db.BDDUsedField{FieldName: "sku", Description: "SKU code"})
	if err != nil {
		t.Fatalf("AddField: %v", err)
	}
	if added.ID == "" {
		t.Error("expected ID to be generated")
	}
	if added.UsedTableID != created.ID {
		t.Errorf("expected UsedTableID=%q, got %q", created.ID, added.UsedTableID)
	}
}

func TestUpdateFieldDescription_Success(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), []db.BDDUsedField{
		{FieldName: "sku", Description: "old"},
	})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	fieldID := created.Fields[0].ID

	if err := repo.UpdateFieldDescription(context.Background(), fieldID, "new desc"); err != nil {
		t.Fatalf("UpdateFieldDescription: %v", err)
	}

	var got db.BDDUsedField
	if err := g.First(&got, "id = ?", fieldID).Error; err != nil {
		t.Fatal(err)
	}
	if got.Description != "new desc" {
		t.Errorf("description not updated: %q", got.Description)
	}
}

func TestUpdateFieldDescription_NotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	err := repo.UpdateFieldDescription(context.Background(), uuid.NewString(), "x")
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}

// TestUpdateFieldDescription_ToEmpty regression-guards against GORM's
// Update("col", val) silently skipping zero-values. We seed a non-empty
// description, then call UpdateFieldDescription with "", and assert
// the column is actually cleared.
func TestUpdateFieldDescription_ToEmpty(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), []db.BDDUsedField{
		{FieldName: "sku", Description: "initial"},
	})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	fieldID := created.Fields[0].ID
	if created.Fields[0].Description != "initial" {
		t.Fatalf("seed description not persisted: %q", created.Fields[0].Description)
	}

	if err := repo.UpdateFieldDescription(context.Background(), fieldID, ""); err != nil {
		t.Fatalf("UpdateFieldDescription to empty: %v", err)
	}

	var got db.BDDUsedField
	if err := g.First(&got, "id = ?", fieldID).Error; err != nil {
		t.Fatal(err)
	}
	if got.Description != "" {
		t.Errorf("expected empty description, got %q", got.Description)
	}
}

func TestDeleteField_Success(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), []db.BDDUsedField{
		{FieldName: "sku"},
		{FieldName: "price"},
	})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	skuID := ""
	for _, f := range created.Fields {
		if f.FieldName == "sku" {
			skuID = f.ID
		}
	}

	if err := repo.DeleteField(context.Background(), skuID); err != nil {
		t.Fatalf("DeleteField: %v", err)
	}

	var count int64
	if err := g.Model(&db.BDDUsedField{}).Where("used_table_id = ?", created.ID).Count(&count).Error; err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Errorf("expected 1 remaining field, got %d", count)
	}
}

func TestDeleteField_NotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	err := repo.DeleteField(context.Background(), uuid.NewString())
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}

func TestResolveByDBAndName_Success(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(7, "contacts"), []db.BDDUsedField{
		{FieldName: "email"},
	}); err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	got, err := repo.ResolveByDBAndName(context.Background(), 7, "contacts")
	if err != nil {
		t.Fatalf("ResolveByDBAndName: %v", err)
	}
	if got.Name != "contacts" || got.DatabaseID != 7 {
		t.Errorf("unexpected payload: %+v", got)
	}
	if len(got.Fields) != 1 {
		t.Errorf("expected 1 preloaded field, got %d", len(got.Fields))
	}
}

func TestResolveByDBAndName_NotFound(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	_, err := repo.ResolveByDBAndName(context.Background(), 999, "ghost")
	if !errors.Is(err, ErrBDDNotFound) {
		t.Fatalf("expected ErrBDDNotFound, got %v", err)
	}
}
