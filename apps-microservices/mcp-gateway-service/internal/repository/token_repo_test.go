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

// TestNewTokenRepoNilInputs ensures the constructor doesn't panic when called
// with nil dependencies — e.g. at boot when encryption isn't configured.
func TestNewTokenRepoNilInputs(t *testing.T) {
	repo := NewTokenRepo(nil, nil)
	if repo == nil {
		t.Error("expected non-nil repo")
	}
}

func TestNewTokenRepo(t *testing.T) {
	repo := NewTokenRepo(nil, nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}

// setupTokenBDDTestDB creates an in-memory SQLite DB with the minimal DDL
// required to exercise UpdateBDDTables / preload roundtrip. Mirrors the
// MySQL columns from internal/db/models.go but with SQLite-friendly types.
func setupTokenBDDTestDB(t *testing.T) *gorm.DB {
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

	stmts := []string{
		`CREATE TABLE scope_tokens (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			token_hash TEXT NOT NULL,
			token_prefix TEXT NOT NULL DEFAULT '',
			created_by TEXT NOT NULL DEFAULT '',
			mcp_command TEXT NOT NULL DEFAULT 'npx',
			server_name TEXT NOT NULL DEFAULT '',
			allow_http INTEGER NOT NULL DEFAULT 0,
			encrypted_token BLOB,
			expires_at DATETIME,
			is_active INTEGER NOT NULL DEFAULT 1,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			leexi_filter_mode TEXT NOT NULL DEFAULT 'none',
			leexi_allowed_user_uuids TEXT,
			leexi_allowed_team_uuids TEXT
		)`,
		`CREATE TABLE scope_token_servers (
			token_id TEXT NOT NULL,
			server_id TEXT NOT NULL,
			PRIMARY KEY (token_id, server_id),
			FOREIGN KEY (token_id) REFERENCES scope_tokens(id) ON DELETE CASCADE
		)`,
		`CREATE TABLE scope_token_tools (
			token_id TEXT NOT NULL,
			server_id TEXT NOT NULL,
			tool_name TEXT NOT NULL,
			PRIMARY KEY (token_id, server_id, tool_name),
			FOREIGN KEY (token_id) REFERENCES scope_tokens(id) ON DELETE CASCADE
		)`,
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
		`CREATE TABLE scope_token_bdd_tables (
			token_id TEXT NOT NULL,
			used_table_id TEXT NOT NULL,
			PRIMARY KEY (token_id, used_table_id),
			FOREIGN KEY (token_id) REFERENCES scope_tokens(id) ON DELETE CASCADE,
			FOREIGN KEY (used_table_id) REFERENCES bdd_used_tables(id) ON DELETE CASCADE
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

// seedTokenAndTables inserts a scope token and N bdd_used_tables rows;
// returns the IDs in the order they were inserted.
func seedTokenAndTables(t *testing.T, g *gorm.DB, tableCount int) (tokenID string, tableIDs []string) {
	t.Helper()
	tokenID = uuid.NewString()
	tk := db.ScopeToken{
		ID:        tokenID,
		Name:      "tok-" + tokenID[:8],
		TokenHash: "hash-" + tokenID,
	}
	if err := g.Create(&tk).Error; err != nil {
		t.Fatalf("seed token: %v", err)
	}
	for i := 0; i < tableCount; i++ {
		id := uuid.NewString()
		row := db.BDDUsedTable{
			ID:         id,
			DatabaseID: i + 1,
			Name:       "tbl_" + id[:6],
		}
		if err := g.Create(&row).Error; err != nil {
			t.Fatalf("seed bdd table: %v", err)
		}
		tableIDs = append(tableIDs, id)
	}
	return tokenID, tableIDs
}

func TestUpdateBDDTables_SetTwo(t *testing.T) {
	g := setupTokenBDDTestDB(t)
	repo := NewTokenRepo(g, nil)
	tokenID, tableIDs := seedTokenAndTables(t, g, 2)

	if err := repo.UpdateBDDTables(context.Background(), tokenID, tableIDs); err != nil {
		t.Fatalf("UpdateBDDTables: %v", err)
	}

	tk, err := repo.GetByID(tokenID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(tk.BDDTables) != 2 {
		t.Fatalf("expected 2 BDDTables, got %d", len(tk.BDDTables))
	}
	got := map[string]bool{}
	for _, b := range tk.BDDTables {
		got[b.UsedTableID] = true
	}
	for _, id := range tableIDs {
		if !got[id] {
			t.Errorf("missing table id %q in roundtrip", id)
		}
	}
}

func TestUpdateBDDTables_ClearWithEmpty(t *testing.T) {
	g := setupTokenBDDTestDB(t)
	repo := NewTokenRepo(g, nil)
	tokenID, tableIDs := seedTokenAndTables(t, g, 2)

	if err := repo.UpdateBDDTables(context.Background(), tokenID, tableIDs); err != nil {
		t.Fatalf("seed UpdateBDDTables: %v", err)
	}
	if err := repo.UpdateBDDTables(context.Background(), tokenID, nil); err != nil {
		t.Fatalf("clear UpdateBDDTables: %v", err)
	}

	tk, err := repo.GetByID(tokenID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(tk.BDDTables) != 0 {
		t.Fatalf("expected 0 BDDTables after clear, got %d", len(tk.BDDTables))
	}
}

func TestUpdateBDDTables_UnknownIDRejected(t *testing.T) {
	g := setupTokenBDDTestDB(t)
	repo := NewTokenRepo(g, nil)
	tokenID, tableIDs := seedTokenAndTables(t, g, 1)

	bogus := uuid.NewString()
	err := repo.UpdateBDDTables(context.Background(), tokenID, []string{tableIDs[0], bogus})
	if !errors.Is(err, ErrBDDTableNotFound) {
		t.Fatalf("expected ErrBDDTableNotFound, got %v", err)
	}

	// Existing rows must be untouched on rejection.
	tk, err := repo.GetByID(tokenID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(tk.BDDTables) != 0 {
		t.Errorf("expected no rows persisted on rejection, got %d", len(tk.BDDTables))
	}
}
