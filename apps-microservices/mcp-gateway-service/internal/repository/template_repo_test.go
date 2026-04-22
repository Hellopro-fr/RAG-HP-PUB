package repository

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// newTemplateTestDB opens an in-memory SQLite and creates minimal tables
// covering the rows exercised by TemplateRepo and InstanceRepo. We avoid
// AutoMigrate on db.Template / db.TemplateInstance / db.MCPServer because their
// MySQL-specific `datetime(3)` column type is not recognised by SQLite drivers
// for time.Time scan conversion.
//
// Only columns actually read/written by the repositories under test are
// declared — this keeps the DDL narrow and easy to evolve. Callers that need
// additional tables can extend this helper in place.
func newTemplateTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE templates (
			slug                TEXT PRIMARY KEY,
			name                TEXT NOT NULL,
			description         TEXT,
			icon                TEXT NOT NULL DEFAULT '',
			stdio_command       TEXT NOT NULL,
			stdio_args          TEXT,
			default_env         TEXT,
			required_extra_env  TEXT,
			tool_prefix         TEXT NOT NULL DEFAULT '',
			tags                TEXT,
			is_active           INTEGER NOT NULL DEFAULT 1,
			created_at          datetime,
			updated_at          datetime
		);
		CREATE TABLE mcp_servers (
			id                   TEXT PRIMARY KEY,
			name                 TEXT NOT NULL DEFAULT '',
			url                  TEXT NOT NULL DEFAULT '',
			transport_preference TEXT NOT NULL DEFAULT 'auto',
			connect_timeout_ms   INTEGER NOT NULL DEFAULT 10000,
			mcp_transport        TEXT NOT NULL DEFAULT 'http',
			tool_prefix          TEXT NOT NULL DEFAULT '',
			icon                 TEXT NOT NULL DEFAULT '',
			is_active            INTEGER NOT NULL DEFAULT 1,
			health_status        TEXT NOT NULL DEFAULT 'unknown',
			created_by           TEXT NOT NULL DEFAULT '',
			created_at           datetime,
			updated_at           datetime
		);
		CREATE TABLE template_instances (
			id                    TEXT PRIMARY KEY,
			template_slug         TEXT NOT NULL,
			name                  TEXT NOT NULL,
			encrypted_credentials BLOB NOT NULL,
			credentials_hash      TEXT NOT NULL,
			extra_env             TEXT,
			runner_port           INTEGER,
			runner_status         TEXT NOT NULL DEFAULT 'pending',
			runner_last_error     TEXT,
			mcp_server_id         TEXT NOT NULL,
			created_by            TEXT NOT NULL DEFAULT '',
			created_at            datetime,
			updated_at            datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create tables: %v", err)
	}
	return gdb
}

func TestTemplateRepo_ListActive(t *testing.T) {
	gdb := newTemplateTestDB(t)
	if err := gdb.Create(&db.Template{Slug: "ga", Name: "GA4", StdioCommand: "analytics-mcp", IsActive: true, Tags: json.RawMessage(`["google"]`)}).Error; err != nil {
		t.Fatalf("seed ga: %v", err)
	}
	if err := gdb.Create(&db.Template{Slug: "gsc", Name: "GSC", StdioCommand: "mcp-gsc", IsActive: true}).Error; err != nil {
		t.Fatalf("seed gsc: %v", err)
	}
	// Bool zero-value + gorm `default:true` tag makes GORM substitute the default on
	// Create, so we bypass GORM for the inactive row to actually store is_active=0.
	if err := gdb.Exec(
		"INSERT INTO templates (slug, name, stdio_command, is_active) VALUES (?, ?, ?, 0)",
		"old", "Old", "x",
	).Error; err != nil {
		t.Fatalf("insert inactive: %v", err)
	}

	repo := NewTemplateRepo(gdb)
	out, err := repo.ListActive()
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 2 {
		t.Errorf("want 2, got %d", len(out))
	}
}

func TestTemplateRepo_ListAll(t *testing.T) {
	gdb := newTemplateTestDB(t)
	if err := gdb.Create(&db.Template{Slug: "ga", Name: "GA4", StdioCommand: "analytics-mcp", IsActive: true}).Error; err != nil {
		t.Fatalf("seed ga: %v", err)
	}
	if err := gdb.Create(&db.Template{Slug: "gsc", Name: "GSC", StdioCommand: "mcp-gsc", IsActive: true}).Error; err != nil {
		t.Fatalf("seed gsc: %v", err)
	}
	// Inactive row inserted via raw SQL — GORM would override is_active=0 with the default:true tag.
	if err := gdb.Exec(
		"INSERT INTO templates (slug, name, stdio_command, is_active) VALUES (?, ?, ?, 0)",
		"old", "Old", "x",
	).Error; err != nil {
		t.Fatalf("insert inactive: %v", err)
	}

	repo := NewTemplateRepo(gdb)
	all, err := repo.ListAll()
	if err != nil {
		t.Fatalf("ListAll err: %v", err)
	}
	if len(all) != 3 {
		t.Errorf("ListAll: want 3 rows, got %d", len(all))
	}
	active, err := repo.ListActive()
	if err != nil {
		t.Fatalf("ListActive err: %v", err)
	}
	if len(active) != 2 {
		t.Errorf("ListActive: want 2 rows, got %d", len(active))
	}
}

func TestTemplateRepo_Upsert(t *testing.T) {
	gdb := newTemplateTestDB(t)
	// Seed one existing row that will be updated by Upsert.
	if err := gdb.Create(&db.Template{
		Slug:         "ga",
		Name:         "GA4 old",
		StdioCommand: "analytics-mcp",
		IsActive:     true,
	}).Error; err != nil {
		t.Fatalf("seed ga: %v", err)
	}

	repo := NewTemplateRepo(gdb)

	// Upsert: update "ga" + insert brand-new "gsc".
	err := repo.Upsert([]db.Template{
		{
			Slug:         "ga",
			Name:         "GA4 updated",
			Description:  "new desc",
			StdioCommand: "analytics-mcp",
			IsActive:     true,
		},
		{
			Slug:         "gsc",
			Name:         "GSC",
			StdioCommand: "mcp-gsc",
			IsActive:     true,
		},
	})
	if err != nil {
		t.Fatalf("Upsert: %v", err)
	}

	// Both rows present.
	all, err := repo.ListAll()
	if err != nil {
		t.Fatalf("ListAll: %v", err)
	}
	if len(all) != 2 {
		t.Fatalf("want 2 rows after upsert, got %d", len(all))
	}
	byslug := map[string]db.Template{}
	for _, row := range all {
		byslug[row.Slug] = row
	}
	if byslug["ga"].Name != "GA4 updated" {
		t.Errorf("ga.Name = %q, want %q", byslug["ga"].Name, "GA4 updated")
	}
	if byslug["ga"].Description != "new desc" {
		t.Errorf("ga.Description = %q, want %q", byslug["ga"].Description, "new desc")
	}
	if byslug["gsc"].Name != "GSC" {
		t.Errorf("gsc.Name = %q, want %q", byslug["gsc"].Name, "GSC")
	}
}

func TestTemplateRepo_GetBySlug_NotFound(t *testing.T) {
	gdb := newTemplateTestDB(t)
	repo := NewTemplateRepo(gdb)
	_, err := repo.GetBySlug("nope")
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		t.Fatalf("want gorm.ErrRecordNotFound, got %v", err)
	}
}

// newTestEncryptor returns an Encryptor with a deterministic test-only key.
// Not used in production.
func newTestEncryptor(t *testing.T) *crypto.Encryptor {
	t.Helper()
	// 32-byte hex key
	enc, err := crypto.NewEncryptor("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	if err != nil {
		t.Fatalf("encryptor: %v", err)
	}
	return enc
}

func TestInstanceRepo_CreateRoundTrip(t *testing.T) {
	gdb := newTemplateTestDB(t)
	enc := newTestEncryptor(t)
	repo := NewInstanceRepo(gdb, enc)

	credJSON := []byte(`{"type":"service_account","client_email":"a@b.iam.gserviceaccount.com"}`)
	hash := sha256.Sum256(credJSON)

	inst := &db.TemplateInstance{
		ID:              uuid.New().String(),
		TemplateSlug:    "ga",
		Name:            "HelloPro prod",
		CredentialsHash: hex.EncodeToString(hash[:]),
		MCPServerID:     uuid.New().String(),
		RunnerStatus:    "pending",
	}
	if err := repo.Create(inst, credJSON); err != nil {
		t.Fatalf("create: %v", err)
	}

	got, plaintext, err := repo.GetByIDWithCredentials(inst.ID)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if got.Name != "HelloPro prod" {
		t.Errorf("Name = %q", got.Name)
	}
	if string(plaintext) != string(credJSON) {
		t.Errorf("plaintext round-trip failed")
	}
	if len(got.EncryptedCredentials) == 0 {
		t.Error("EncryptedCredentials is empty — encryption didn't run")
	}
	if string(got.EncryptedCredentials) == string(credJSON) {
		t.Error("EncryptedCredentials equals plaintext — encryption silently bypassed")
	}
}

func TestInstanceRepo_DeleteWithMCPServer(t *testing.T) {
	gdb := newTemplateTestDB(t)
	enc := newTestEncryptor(t)
	repo := NewInstanceRepo(gdb, enc)

	instID := uuid.New().String()
	serverID := uuid.New().String()

	// Seed an mcp_servers row that the instance will reference
	if err := gdb.Exec(
		"INSERT INTO mcp_servers (id, name, url) VALUES (?, ?, ?)",
		serverID, "test-srv", "http://test",
	).Error; err != nil {
		t.Fatalf("seed mcp_server: %v", err)
	}

	// Seed the instance via repo.Create
	inst := &db.TemplateInstance{
		ID:              instID,
		TemplateSlug:    "ga",
		Name:            "to-delete",
		CredentialsHash: "h",
		MCPServerID:     serverID,
		RunnerStatus:    "running",
	}
	if err := repo.Create(inst, []byte(`{"type":"service_account"}`)); err != nil {
		t.Fatalf("create: %v", err)
	}

	// Delete
	if err := repo.DeleteWithMCPServer(instID); err != nil {
		t.Fatalf("delete: %v", err)
	}

	// Both rows should be gone
	if _, err := repo.GetByID(instID); !errors.Is(err, gorm.ErrRecordNotFound) {
		t.Errorf("instance should be gone, got err %v", err)
	}
	var cnt int64
	gdb.Raw("SELECT COUNT(*) FROM mcp_servers WHERE id = ?", serverID).Scan(&cnt)
	if cnt != 0 {
		t.Errorf("mcp_server should be gone, count = %d", cnt)
	}
}

func TestInstanceRepo_FindByMCPServerID(t *testing.T) {
	gdb := newTemplateTestDB(t)
	enc := newTestEncryptor(t)
	repo := NewInstanceRepo(gdb, enc)

	serverID := uuid.New().String()
	instID := uuid.New().String()
	inst := &db.TemplateInstance{
		ID:              instID,
		TemplateSlug:    "ga",
		Name:            "test",
		CredentialsHash: "h",
		MCPServerID:     serverID,
		RunnerStatus:    "running",
	}
	if err := repo.Create(inst, []byte(`{}`)); err != nil {
		t.Fatalf("create: %v", err)
	}

	got, err := repo.FindByMCPServerID(serverID)
	if err != nil {
		t.Fatalf("find: %v", err)
	}
	if got.ID != instID {
		t.Errorf("ID = %q, want %q", got.ID, instID)
	}

	// Server that has no template instance backing it → ErrRecordNotFound.
	if _, err := repo.FindByMCPServerID(uuid.New().String()); !errors.Is(err, gorm.ErrRecordNotFound) {
		t.Errorf("want ErrRecordNotFound for missing server, got %v", err)
	}
}

func TestInstanceRepo_CountsByTemplate(t *testing.T) {
	gdb := newTemplateTestDB(t)
	enc := newTestEncryptor(t)
	repo := NewInstanceRepo(gdb, enc)

	// Empty table → empty map, no error.
	m, err := repo.CountsByTemplate()
	if err != nil {
		t.Fatalf("empty counts: %v", err)
	}
	if len(m) != 0 {
		t.Errorf("empty table should produce empty map, got %v", m)
	}

	// Seed 2 instances for "ga", 1 for "gsc".
	seed := []struct {
		slug string
		name string
	}{
		{"ga", "ga-1"},
		{"ga", "ga-2"},
		{"gsc", "gsc-1"},
	}
	for _, s := range seed {
		inst := &db.TemplateInstance{
			ID:              uuid.New().String(),
			TemplateSlug:    s.slug,
			Name:            s.name,
			CredentialsHash: "h",
			MCPServerID:     uuid.New().String(),
			RunnerStatus:    "running",
		}
		if err := repo.Create(inst, []byte(`{}`)); err != nil {
			t.Fatalf("seed %s: %v", s.name, err)
		}
	}

	m, err = repo.CountsByTemplate()
	if err != nil {
		t.Fatalf("counts: %v", err)
	}
	if m["ga"] != 2 {
		t.Errorf("ga count = %d, want 2", m["ga"])
	}
	if m["gsc"] != 1 {
		t.Errorf("gsc count = %d, want 1", m["gsc"])
	}
	if _, ok := m["nonexistent"]; ok {
		t.Errorf("unexpected slug in counts: %v", m)
	}
}

func TestInstanceRepo_DeleteWithMCPServer_MissingServer(t *testing.T) {
	// The instance's MCPServerID points to a non-existent mcp_servers row.
	// Delete should still succeed — tx.Delete on a missing row is a no-op in GORM.
	gdb := newTemplateTestDB(t)
	enc := newTestEncryptor(t)
	repo := NewInstanceRepo(gdb, enc)

	instID := uuid.New().String()
	inst := &db.TemplateInstance{
		ID:              instID,
		TemplateSlug:    "ga",
		Name:            "orphan",
		CredentialsHash: "h",
		MCPServerID:     uuid.New().String(), // never inserted
		RunnerStatus:    "running",
	}
	if err := repo.Create(inst, []byte(`{}`)); err != nil {
		t.Fatalf("create: %v", err)
	}

	if err := repo.DeleteWithMCPServer(instID); err != nil {
		t.Fatalf("delete orphan: %v", err)
	}
	if _, err := repo.GetByID(instID); !errors.Is(err, gorm.ErrRecordNotFound) {
		t.Errorf("instance should be gone, got err %v", err)
	}
}
