package repository

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"mcp-gateway/internal/db"
)

// setupBDDTestDB creates an in-memory SQLite DB with a manual DDL that
// mirrors internal/db/models.go (BDDUsedTable + BDDUsedField, plus the
// scope_token_bdd_tables / oauth2_client_bdd_tables join tables that
// DeleteTable now clears). Manual DDL is required because the GORM
// `datetime(3)` MySQL-only tags are incompatible with SQLite.
//
// The two join tables are intentionally minimal: composite PK only, no
// FK constraint pointing at bdd_used_tables. This matches production
// (the GORM models do not declare a back-reference cascade) and is
// what makes the application-level cascade in DeleteTable necessary.
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
			rows INTEGER,
			primary_key TEXT NOT NULL DEFAULT '',
			default_order_by TEXT NOT NULL DEFAULT '',
			relations TEXT,
			notes TEXT,
			is_active INTEGER NOT NULL DEFAULT 1,
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
			field_type TEXT NOT NULL DEFAULT '',
			description TEXT,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			UNIQUE (used_table_id, field_name),
			FOREIGN KEY (used_table_id) REFERENCES bdd_used_tables(id) ON DELETE CASCADE
		)`,
		`CREATE INDEX idx_bdd_used_fields_used_table_id ON bdd_used_fields(used_table_id)`,
		`CREATE INDEX idx_bdd_used_fields_upstream_field_id ON bdd_used_fields(upstream_field_id)`,
		`CREATE TABLE scope_token_bdd_tables (
			token_id TEXT NOT NULL,
			used_table_id TEXT NOT NULL,
			PRIMARY KEY (token_id, used_table_id)
		)`,
		`CREATE TABLE oauth2_client_bdd_tables (
			client_id TEXT NOT NULL,
			used_table_id TEXT NOT NULL,
			PRIMARY KEY (client_id, used_table_id)
		)`,
		`CREATE TABLE bdd_meta (
			id INTEGER PRIMARY KEY,
			description TEXT,
			usage TEXT,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_by TEXT NOT NULL DEFAULT ''
		)`,
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
	got, total, err := repo.ListTables(context.Background(), ListTablesOptions{DatabaseID: &one, Limit: 50})
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if total != 1 || len(got) != 1 {
		t.Fatalf("expected 1 row for db1, got len=%d total=%d", len(got), total)
	}
	if got[0].Name != "products" {
		t.Errorf("unexpected row: %+v", got[0])
	}

	five := 5
	gotFive, totalFive, err := repo.ListTables(context.Background(), ListTablesOptions{DatabaseID: &five, Limit: 50})
	if err != nil {
		t.Fatalf("ListTables db5: %v", err)
	}
	if totalFive != 2 || len(gotFive) != 2 {
		t.Fatalf("expected 2 rows for db5, got len=%d total=%d", len(gotFive), totalFive)
	}
	names := map[string]bool{gotFive[0].Name: true, gotFive[1].Name: true}
	if !names["deals"] || !names["leads"] {
		t.Errorf("expected deals + leads, got %+v", gotFive)
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

	got, total, err := repo.ListTables(context.Background(), ListTablesOptions{Search: "PrOd", Limit: 50})
	if err != nil {
		t.Fatalf("ListTables search: %v", err)
	}
	if total != 2 || len(got) != 2 {
		t.Fatalf("expected 2 hits (products + leads via description), got len=%d total=%d", len(got), total)
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

// TestDeleteTable_CascadesScopeTokenJoinRows checks that deleting a
// used-table also drops scope_token_bdd_tables rows that reference it.
// The GORM model does not declare a FK cascade for that join, so the
// repository wraps the deletes in a transaction.
func TestDeleteTable_CascadesScopeTokenJoinRows(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}

	// Seed a join row referencing the used table.
	tokenID := uuid.NewString()
	if err := g.Create(&db.ScopeTokenBDDTable{TokenID: tokenID, UsedTableID: created.ID}).Error; err != nil {
		t.Fatalf("seed join row: %v", err)
	}

	if err := repo.DeleteTable(context.Background(), created.ID); err != nil {
		t.Fatalf("DeleteTable: %v", err)
	}

	var leftover int64
	if err := g.Model(&db.ScopeTokenBDDTable{}).
		Where("used_table_id = ?", created.ID).
		Count(&leftover).Error; err != nil {
		t.Fatalf("count leftover scope-token join rows: %v", err)
	}
	if leftover != 0 {
		t.Errorf("expected 0 leftover scope_token_bdd_tables rows, got %d", leftover)
	}
}

// TestDeleteTable_CascadesOAuth2JoinRows is the OAuth2 client mirror of
// TestDeleteTable_CascadesScopeTokenJoinRows.
func TestDeleteTable_CascadesOAuth2JoinRows(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	created, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}

	clientID := uuid.NewString()
	if err := g.Create(&db.OAuth2ClientBDDTable{ClientID: clientID, UsedTableID: created.ID}).Error; err != nil {
		t.Fatalf("seed join row: %v", err)
	}

	if err := repo.DeleteTable(context.Background(), created.ID); err != nil {
		t.Fatalf("DeleteTable: %v", err)
	}

	var leftover int64
	if err := g.Model(&db.OAuth2ClientBDDTable{}).
		Where("used_table_id = ?", created.ID).
		Count(&leftover).Error; err != nil {
		t.Fatalf("count leftover oauth2 join rows: %v", err)
	}
	if leftover != 0 {
		t.Errorf("expected 0 leftover oauth2_client_bdd_tables rows, got %d", leftover)
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

// TestListTables_Pagination_HappyPath inserts 25 rows and verifies that
// page 1, 2, 3 with limit=10 produce 10, 10, 5 rows and a stable total
// of 25 across the three calls.
func TestListTables_Pagination_HappyPath(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	for i := 0; i < 25; i++ {
		// Distinct names so the unique constraint doesn't reject inserts.
		name := fmt.Sprintf("tbl_%02d", i)
		if _, err := repo.CreateTable(context.Background(), newTable(1, name), nil); err != nil {
			t.Fatalf("seed %s: %v", name, err)
		}
	}

	page1, total1, err := repo.ListTables(context.Background(), ListTablesOptions{Limit: 10, Offset: 0})
	if err != nil {
		t.Fatalf("page1: %v", err)
	}
	if total1 != 25 || len(page1) != 10 {
		t.Fatalf("page1: total=%d len=%d want total=25 len=10", total1, len(page1))
	}

	page2, total2, err := repo.ListTables(context.Background(), ListTablesOptions{Limit: 10, Offset: 10})
	if err != nil {
		t.Fatalf("page2: %v", err)
	}
	if total2 != 25 || len(page2) != 10 {
		t.Fatalf("page2: total=%d len=%d want total=25 len=10", total2, len(page2))
	}

	page3, total3, err := repo.ListTables(context.Background(), ListTablesOptions{Limit: 10, Offset: 20})
	if err != nil {
		t.Fatalf("page3: %v", err)
	}
	if total3 != 25 || len(page3) != 5 {
		t.Fatalf("page3: total=%d len=%d want total=25 len=5", total3, len(page3))
	}
}

// TestListTables_Pagination_OrderedByCreatedDesc verifies that the
// newest row surfaces first. We insert two rows with a deliberate sleep
// between them so SQLite's CURRENT_TIMESTAMP resolution is wide enough
// to order them deterministically.
func TestListTables_Pagination_OrderedByCreatedDesc(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "first"), nil); err != nil {
		t.Fatalf("first: %v", err)
	}
	// CURRENT_TIMESTAMP in SQLite resolves to seconds — sleep long enough
	// that the second row's created_at is strictly greater.
	time.Sleep(1100 * time.Millisecond)
	if _, err := repo.CreateTable(context.Background(), newTable(1, "second"), nil); err != nil {
		t.Fatalf("second: %v", err)
	}

	rows, total, err := repo.ListTables(context.Background(), ListTablesOptions{Limit: 50})
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if total != 2 || len(rows) != 2 {
		t.Fatalf("len=%d total=%d want 2/2", len(rows), total)
	}
	if rows[0].Name != "second" || rows[1].Name != "first" {
		t.Errorf("expected [second, first], got [%s, %s]", rows[0].Name, rows[1].Name)
	}
}

// TestListTables_AllDatabases_NilDatabaseID verifies that a nil
// DatabaseID does NOT scope the result and returns rows from every
// database. Regression guard against an earlier shape where 0 (Go's
// zero value for int) was treated as a real filter.
func TestListTables_AllDatabases_NilDatabaseID(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "tbl_one"), nil); err != nil {
		t.Fatal(err)
	}
	if _, err := repo.CreateTable(context.Background(), newTable(5, "tbl_five"), nil); err != nil {
		t.Fatal(err)
	}

	rows, total, err := repo.ListTables(context.Background(), ListTablesOptions{Limit: 50})
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if total != 2 || len(rows) != 2 {
		t.Fatalf("len=%d total=%d want 2/2", len(rows), total)
	}
}

// TestBulkCreate_Mixed exercises the per-item validation path: 2 valid
// names + 1 invalid name in the same batch should produce 2 created
// rows and 1 error entry without aborting the transaction.
//
// The bad-name validation lives in the API layer (the repo accepts any
// string), so this test simulates only what the repo can decide on its
// own — duplicate detection. See TestBulkCreate_DuplicateTable.
func TestBulkCreate_Mixed(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	results, err := repo.BulkCreate(context.Background(), 1, []BulkCreateItem{
		{TableName: "good_one"},
		{TableName: "good_two"},
		{TableName: "good_three"},
	}, "tester@hellopro.fr")
	if err != nil {
		t.Fatalf("BulkCreate: %v", err)
	}
	if len(results) != 3 {
		t.Fatalf("len(results)=%d want=3", len(results))
	}
	for i, r := range results {
		if r.Err != nil {
			t.Errorf("results[%d] unexpected error: %v", i, r.Err)
		}
		if r.Table == nil {
			t.Errorf("results[%d] missing table", i)
		}
	}
}

// TestBulkCreate_DuplicateTable seeds one row, then asks BulkCreate to
// insert two rows where the first collides with the seed. The colliding
// row must surface ErrBDDDuplicateTable while the other row succeeds.
func TestBulkCreate_DuplicateTable(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "products"), nil); err != nil {
		t.Fatalf("seed: %v", err)
	}

	results, err := repo.BulkCreate(context.Background(), 1, []BulkCreateItem{
		{TableName: "products"},
		{TableName: "fresh_table"},
	}, "tester@hellopro.fr")
	if err != nil {
		t.Fatalf("BulkCreate: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("len(results)=%d want=2", len(results))
	}
	if !errors.Is(results[0].Err, ErrBDDDuplicateTable) {
		t.Errorf("results[0].Err=%v want=ErrBDDDuplicateTable", results[0].Err)
	}
	if results[0].Table != nil {
		t.Errorf("results[0].Table should be nil on duplicate")
	}
	if results[1].Err != nil {
		t.Errorf("results[1].Err=%v want=nil", results[1].Err)
	}
	if results[1].Table == nil || results[1].Table.Name != "fresh_table" {
		t.Errorf("results[1].Table=%+v want fresh_table", results[1].Table)
	}
}

// TestImport_NewRowInserted asserts an import containing a single
// previously-unseen (database_id, name) inserts the row and its fields.
func TestImport_NewRowInserted(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	payload := []db.BDDUsedTable{
		{
			DatabaseID:      1,
			Name:            "products",
			Description:     "main",
			UpstreamTableID: 42,
			Fields: []db.BDDUsedField{
				{FieldName: "id", Description: "pk"},
				{FieldName: "name", Description: "label"},
			},
		},
	}
	inserted, updated, errs, err := repo.Import(context.Background(), payload, "tester@hellopro.fr")
	if err != nil {
		t.Fatalf("Import: %v", err)
	}
	if inserted != 1 || updated != 0 || len(errs) != 0 {
		t.Fatalf("inserted=%d updated=%d errs=%v", inserted, updated, errs)
	}

	got, err := repo.ResolveByDBAndName(context.Background(), 1, "products")
	if err != nil {
		t.Fatalf("ResolveByDBAndName: %v", err)
	}
	if got.UpstreamTableID != 42 || len(got.Fields) != 2 {
		t.Errorf("post-import row: %+v", got)
	}
}

// TestImport_UpsertReplacesFields seeds a row with two fields, then
// imports the same (database_id, name) with a single (different) field.
// The pre-existing field set must be wiped and replaced atomically.
func TestImport_UpsertReplacesFields(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)

	if _, err := repo.CreateTable(context.Background(), newTable(1, "products"), []db.BDDUsedField{
		{FieldName: "id"},
		{FieldName: "name"},
	}); err != nil {
		t.Fatalf("seed: %v", err)
	}

	payload := []db.BDDUsedTable{
		{
			DatabaseID:  1,
			Name:        "products",
			Description: "rewritten",
			Fields: []db.BDDUsedField{
				{FieldName: "sku", Description: "stock keeping unit"},
			},
		},
	}
	inserted, updated, errs, err := repo.Import(context.Background(), payload, "tester@hellopro.fr")
	if err != nil {
		t.Fatalf("Import: %v", err)
	}
	if inserted != 0 || updated != 1 || len(errs) != 0 {
		t.Fatalf("inserted=%d updated=%d errs=%v", inserted, updated, errs)
	}

	got, err := repo.ResolveByDBAndName(context.Background(), 1, "products")
	if err != nil {
		t.Fatalf("ResolveByDBAndName: %v", err)
	}
	if got.Description != "rewritten" {
		t.Errorf("description=%q want=rewritten", got.Description)
	}
	if len(got.Fields) != 1 || got.Fields[0].FieldName != "sku" {
		t.Errorf("fields=%+v want=[sku]", got.Fields)
	}
}

func TestSyncFieldTypes_UpdatesOnlyMatchingChangedFields(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)
	ctx := context.Background()

	tbl := newTable(1, "products")
	fields := []db.BDDUsedField{
		{FieldName: "id", FieldType: ""},       // empty -> filled
		{FieldName: "name", FieldType: "text"}, // identical -> skipped
		{FieldName: "price", FieldType: "old"}, // differs -> updated
		{FieldName: "extra", FieldType: ""},    // absent from map -> untouched
	}
	created, err := repo.CreateTable(ctx, tbl, fields)
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}

	typesByName := map[string]string{
		"id":    "int",
		"name":  "text",
		"price": "decimal",
		"ghost": "varchar", // not a registered field -> ignored
	}
	updated, err := repo.SyncFieldTypes(ctx, created.ID, typesByName)
	if err != nil {
		t.Fatalf("SyncFieldTypes: %v", err)
	}
	if updated != 2 {
		t.Fatalf("updated=%d want=2", updated)
	}

	got, err := repo.GetTable(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetTable: %v", err)
	}
	byName := map[string]string{}
	for _, f := range got.Fields {
		byName[f.FieldName] = f.FieldType
	}
	want := map[string]string{"id": "int", "name": "text", "price": "decimal", "extra": ""}
	for n, w := range want {
		if byName[n] != w {
			t.Errorf("field %q type=%q want=%q", n, byName[n], w)
		}
	}
}

func TestSyncFieldTypes_EmptyMapNoop(t *testing.T) {
	g := setupBDDTestDB(t)
	repo := NewBDDUsedRepo(g)
	ctx := context.Background()

	created, err := repo.CreateTable(ctx, newTable(1, "products"),
		[]db.BDDUsedField{{FieldName: "id", FieldType: "int"}})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	updated, err := repo.SyncFieldTypes(ctx, created.ID, nil)
	if err != nil {
		t.Fatalf("SyncFieldTypes: %v", err)
	}
	if updated != 0 {
		t.Fatalf("updated=%d want=0", updated)
	}
}
