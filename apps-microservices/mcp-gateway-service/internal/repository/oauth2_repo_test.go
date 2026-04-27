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

func TestNewOAuth2Repo(t *testing.T) {
	repo := NewOAuth2Repo(nil, nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}

// setupOAuth2BDDTestDB mirrors setupTokenBDDTestDB but for the OAuth2 client
// schema. Manual DDL because the production tags use MySQL-only types.
func setupOAuth2BDDTestDB(t *testing.T) *gorm.DB {
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
		`CREATE TABLE oauth2_clients (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			secret_hash TEXT NOT NULL,
			secret_prefix TEXT NOT NULL DEFAULT '',
			encrypted_secret BLOB,
			redirect_uris TEXT,
			grant_types TEXT,
			token_auth_method TEXT NOT NULL DEFAULT 'client_secret_post',
			dynamically_registered INTEGER NOT NULL DEFAULT 0,
			access_token_ttl INTEGER NOT NULL DEFAULT 3600,
			expires_at DATETIME,
			is_active INTEGER NOT NULL DEFAULT 1,
			created_by TEXT NOT NULL DEFAULT '',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			leexi_filter_mode TEXT NOT NULL DEFAULT 'none',
			leexi_allowed_user_uuids TEXT,
			leexi_allowed_team_uuids TEXT,
			ringover_filter_mode TEXT NOT NULL DEFAULT 'none',
			ringover_allowed_user_ids TEXT,
			ringover_allowed_team_ids TEXT
		)`,
		`CREATE TABLE oauth2_client_servers (
			client_id TEXT NOT NULL,
			server_id TEXT NOT NULL,
			PRIMARY KEY (client_id, server_id),
			FOREIGN KEY (client_id) REFERENCES oauth2_clients(id) ON DELETE CASCADE
		)`,
		`CREATE TABLE oauth2_client_tools (
			client_id TEXT NOT NULL,
			server_id TEXT NOT NULL,
			tool_name TEXT NOT NULL,
			PRIMARY KEY (client_id, server_id, tool_name),
			FOREIGN KEY (client_id) REFERENCES oauth2_clients(id) ON DELETE CASCADE
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
		`CREATE TABLE oauth2_client_bdd_tables (
			client_id TEXT NOT NULL,
			used_table_id TEXT NOT NULL,
			PRIMARY KEY (client_id, used_table_id),
			FOREIGN KEY (client_id) REFERENCES oauth2_clients(id) ON DELETE CASCADE,
			FOREIGN KEY (used_table_id) REFERENCES bdd_used_tables(id) ON DELETE CASCADE
		)`,
		`CREATE TABLE oauth2_client_instructions (
			client_id TEXT NOT NULL,
			instruction_id TEXT NOT NULL,
			PRIMARY KEY (client_id, instruction_id)
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

func seedClientAndTables(t *testing.T, g *gorm.DB, tableCount int) (clientID string, tableIDs []string) {
	t.Helper()
	clientID = uuid.NewString()
	cl := db.OAuth2Client{
		ID:         clientID,
		Name:       "client-" + clientID[:8],
		SecretHash: "hash-" + clientID,
	}
	if err := g.Create(&cl).Error; err != nil {
		t.Fatalf("seed client: %v", err)
	}
	for i := 0; i < tableCount; i++ {
		id := uuid.NewString()
		row := db.BDDUsedTable{
			ID:         id,
			DatabaseID: 100 + i,
			Name:       "tbl_" + id[:6],
		}
		if err := g.Create(&row).Error; err != nil {
			t.Fatalf("seed bdd table: %v", err)
		}
		tableIDs = append(tableIDs, id)
	}
	return clientID, tableIDs
}

func TestOAuth2_UpdateBDDTables_SetTwo(t *testing.T) {
	g := setupOAuth2BDDTestDB(t)
	repo := NewOAuth2Repo(g, nil)
	clientID, tableIDs := seedClientAndTables(t, g, 2)

	if err := repo.UpdateBDDTables(context.Background(), clientID, tableIDs); err != nil {
		t.Fatalf("UpdateBDDTables: %v", err)
	}

	cl, err := repo.GetByID(clientID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(cl.BDDTables) != 2 {
		t.Fatalf("expected 2 BDDTables, got %d", len(cl.BDDTables))
	}
	got := map[string]bool{}
	for _, b := range cl.BDDTables {
		got[b.UsedTableID] = true
	}
	for _, id := range tableIDs {
		if !got[id] {
			t.Errorf("missing table id %q in roundtrip", id)
		}
	}
}

func TestOAuth2_UpdateBDDTables_ClearWithEmpty(t *testing.T) {
	g := setupOAuth2BDDTestDB(t)
	repo := NewOAuth2Repo(g, nil)
	clientID, tableIDs := seedClientAndTables(t, g, 2)

	if err := repo.UpdateBDDTables(context.Background(), clientID, tableIDs); err != nil {
		t.Fatalf("seed UpdateBDDTables: %v", err)
	}
	if err := repo.UpdateBDDTables(context.Background(), clientID, nil); err != nil {
		t.Fatalf("clear UpdateBDDTables: %v", err)
	}

	cl, err := repo.GetByID(clientID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(cl.BDDTables) != 0 {
		t.Fatalf("expected 0 BDDTables after clear, got %d", len(cl.BDDTables))
	}
}

func TestOAuth2_UpdateBDDTables_UnknownIDRejected(t *testing.T) {
	g := setupOAuth2BDDTestDB(t)
	repo := NewOAuth2Repo(g, nil)
	clientID, tableIDs := seedClientAndTables(t, g, 1)

	bogus := uuid.NewString()
	err := repo.UpdateBDDTables(context.Background(), clientID, []string{tableIDs[0], bogus})
	if !errors.Is(err, ErrBDDTableNotFound) {
		t.Fatalf("expected ErrBDDTableNotFound, got %v", err)
	}

	cl, err := repo.GetByID(clientID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(cl.BDDTables) != 0 {
		t.Errorf("expected no rows persisted on rejection, got %d", len(cl.BDDTables))
	}
}

// TestOAuth2_UpdateBDDTables_DedupesDuplicates is the OAuth2 mirror of
// TestUpdateBDDTables_DedupesDuplicates. See that test for context.
func TestOAuth2_UpdateBDDTables_DedupesDuplicates(t *testing.T) {
	g := setupOAuth2BDDTestDB(t)
	repo := NewOAuth2Repo(g, nil)
	clientID, tableIDs := seedClientAndTables(t, g, 2)

	dup := []string{tableIDs[0], tableIDs[0], tableIDs[1]}
	if err := repo.UpdateBDDTables(context.Background(), clientID, dup); err != nil {
		t.Fatalf("UpdateBDDTables with duplicates: %v", err)
	}

	cl, err := repo.GetByID(clientID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(cl.BDDTables) != 2 {
		t.Fatalf("expected 2 join rows after dedupe, got %d", len(cl.BDDTables))
	}
	got := map[string]int{}
	for _, b := range cl.BDDTables {
		got[b.UsedTableID]++
	}
	for _, id := range tableIDs {
		if got[id] != 1 {
			t.Errorf("expected exactly one join row for id=%q, got %d", id, got[id])
		}
	}
}
