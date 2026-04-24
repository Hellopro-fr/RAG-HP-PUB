package repository

import (
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

// newInstructionTestDB creates the tables exercised by InstructionRepo tests.
// Mirrors the narrow-DDL pattern in newTemplateTestDB — AutoMigrate on the
// real GORM models isn't portable to SQLite (datetime(3)) so we hand-roll DDL.
func newInstructionTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE llm_instructions (
			id          TEXT PRIMARY KEY,
			title       TEXT NOT NULL,
			body        TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			created_by  TEXT NOT NULL DEFAULT '',
			created_at  datetime,
			updated_at  datetime
		);
		CREATE TABLE llm_instruction_rows (
			id             TEXT PRIMARY KEY,
			instruction_id TEXT NOT NULL,
			kind           TEXT NOT NULL DEFAULT 'per_server',
			title          TEXT NOT NULL DEFAULT '',
			body           TEXT NOT NULL,
			display_order  INTEGER NOT NULL DEFAULT 0,
			created_at     datetime,
			updated_at     datetime
		);
		CREATE TABLE llm_instruction_row_servers (
			row_id    TEXT NOT NULL,
			server_id TEXT NOT NULL,
			PRIMARY KEY (row_id, server_id)
		);
		CREATE TABLE scope_token_instructions (
			token_id       TEXT NOT NULL,
			instruction_id TEXT NOT NULL,
			PRIMARY KEY (token_id, instruction_id)
		);
		CREATE TABLE oauth2_client_instructions (
			client_id      TEXT NOT NULL,
			instruction_id TEXT NOT NULL,
			PRIMARY KEY (client_id, instruction_id)
		);
		CREATE TABLE mcp_servers (
			id   TEXT PRIMARY KEY,
			name TEXT NOT NULL DEFAULT ''
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create tables: %v", err)
	}
	return gdb
}

func seedServer(t *testing.T, gdb *gorm.DB, id string) {
	t.Helper()
	if err := gdb.Exec("INSERT INTO mcp_servers (id, name) VALUES (?, ?)", id, "srv-"+id).Error; err != nil {
		t.Fatalf("seed server %s: %v", id, err)
	}
}

func TestInstructionRepo_CreateAndGet(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)

	serverA := uuid.New().String()
	serverB := uuid.New().String()
	seedServer(t, gdb, serverA)
	seedServer(t, gdb, serverB)

	created, err := repo.Create("My page", "page description", []RowInput{
		{Title: "Row 1", Body: "First body", ServerIDs: []string{serverA, serverB}},
		{Title: "Row 2", Body: "Second body", ServerIDs: []string{serverA}},
	}, "admin@example.com")
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if created.ID == "" || created.Title != "My page" || created.Description != "page description" {
		t.Errorf("page fields mismatch: %+v", created)
	}
	if len(created.Rows) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(created.Rows))
	}
	if created.Rows[0].Title != "Row 1" || created.Rows[0].DisplayOrder != 0 {
		t.Errorf("row[0] mismatch: %+v", created.Rows[0])
	}
	if created.Rows[1].Title != "Row 2" || created.Rows[1].DisplayOrder != 1 {
		t.Errorf("row[1] mismatch: %+v", created.Rows[1])
	}
	if len(created.Rows[0].Servers) != 2 || len(created.Rows[1].Servers) != 1 {
		t.Errorf("row-server link count wrong: row0=%d row1=%d", len(created.Rows[0].Servers), len(created.Rows[1].Servers))
	}

	got, err := repo.GetByID(created.ID)
	if err != nil {
		t.Fatalf("GetByID: %v", err)
	}
	if len(got.Rows) != 2 {
		t.Errorf("GetByID row count mismatch: %d", len(got.Rows))
	}
}

func TestInstructionRepo_Update_ReplacesRows(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	c := uuid.New().String()
	for _, s := range []string{a, b, c} {
		seedServer(t, gdb, s)
	}

	created, err := repo.Create("P", "", []RowInput{
		{Title: "old", Body: "X", ServerIDs: []string{a}},
	}, "")
	if err != nil {
		t.Fatal(err)
	}

	if err := repo.Update(created.ID, "P v2", "new desc", []RowInput{
		{Title: "new1", Body: "Y", ServerIDs: []string{b}},
		{Title: "new2", Body: "Z", ServerIDs: []string{b, c}},
	}); err != nil {
		t.Fatalf("Update: %v", err)
	}

	got, err := repo.GetByID(created.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Title != "P v2" || got.Description != "new desc" {
		t.Errorf("page fields not updated: %+v", got)
	}
	if len(got.Rows) != 2 {
		t.Fatalf("expected 2 rows after update, got %d", len(got.Rows))
	}
	if got.Rows[0].Title != "new1" || got.Rows[1].Title != "new2" {
		t.Errorf("row titles wrong: %+v", got.Rows)
	}

	// No orphan row-server rows remain.
	var orphanCount int64
	gdb.Raw(`SELECT COUNT(*) FROM llm_instruction_row_servers
	          WHERE row_id NOT IN (SELECT id FROM llm_instruction_rows)`).Scan(&orphanCount)
	if orphanCount != 0 {
		t.Errorf("expected 0 orphan row_server rows, got %d", orphanCount)
	}
}

func TestInstructionRepo_Delete(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	seedServer(t, gdb, a)

	created, err := repo.Create("P", "", []RowInput{{Title: "r", Body: "B", ServerIDs: []string{a}}}, "")
	if err != nil {
		t.Fatal(err)
	}

	// Seed junction rows to verify cascade.
	if err := gdb.Exec("INSERT INTO scope_token_instructions (token_id, instruction_id) VALUES (?, ?)",
		uuid.New().String(), created.ID).Error; err != nil {
		t.Fatal(err)
	}
	if err := gdb.Exec("INSERT INTO oauth2_client_instructions (client_id, instruction_id) VALUES (?, ?)",
		uuid.New().String(), created.ID).Error; err != nil {
		t.Fatal(err)
	}

	if err := repo.Delete(created.ID); err != nil {
		t.Fatalf("Delete: %v", err)
	}

	var cnt int64
	gdb.Raw("SELECT COUNT(*) FROM llm_instructions WHERE id = ?", created.ID).Scan(&cnt)
	if cnt != 0 {
		t.Errorf("page row should be deleted, got %d", cnt)
	}
	gdb.Raw("SELECT COUNT(*) FROM llm_instruction_rows WHERE instruction_id = ?", created.ID).Scan(&cnt)
	if cnt != 0 {
		t.Errorf("rows should be deleted, got %d", cnt)
	}
	gdb.Raw("SELECT COUNT(*) FROM scope_token_instructions WHERE instruction_id = ?", created.ID).Scan(&cnt)
	if cnt != 0 {
		t.Errorf("scope_token_instructions should be deleted, got %d", cnt)
	}
	gdb.Raw("SELECT COUNT(*) FROM oauth2_client_instructions WHERE instruction_id = ?", created.ID).Scan(&cnt)
	if cnt != 0 {
		t.Errorf("oauth2_client_instructions should be deleted, got %d", cnt)
	}
}

func TestInstructionRepo_ListByServerIDs_UnionAcrossRows(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	c := uuid.New().String()
	for _, s := range []string{a, b, c} {
		seedServer(t, gdb, s)
	}

	// P1: row1 [A, B]
	// P2: row1 [A]
	// P3: row1 [C]
	p1, _ := repo.Create("P1", "", []RowInput{{Body: "b1", ServerIDs: []string{a, b}}}, "")
	p2, _ := repo.Create("P2", "", []RowInput{{Body: "b2", ServerIDs: []string{a}}}, "")
	p3, _ := repo.Create("P3", "", []RowInput{{Body: "b3", ServerIDs: []string{c}}}, "")

	// Filter [B] — only P1 has a row linked to B.
	got, err := repo.ListByServerIDs([]string{b}, "")
	if err != nil {
		t.Fatalf("ListByServerIDs: %v", err)
	}
	ids := instructionIDSet(got)
	if !ids[p1.ID] || ids[p2.ID] || ids[p3.ID] {
		t.Errorf("[B] should match only P1, got %v", ids)
	}

	// Filter [A, C] — P1, P2 (both have A), P3 (has C).
	got, err = repo.ListByServerIDs([]string{a, c}, "")
	if err != nil {
		t.Fatal(err)
	}
	ids = instructionIDSet(got)
	if !ids[p1.ID] || !ids[p2.ID] || !ids[p3.ID] {
		t.Errorf("[A, C] should match all three, got %v", ids)
	}
}

func TestInstructionRepo_ListByServerIDs_MultiRowPageDedupes(t *testing.T) {
	// A page whose rows together cover several servers must still appear only
	// once in the filter result.
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	for _, s := range []string{a, b} {
		seedServer(t, gdb, s)
	}
	p, _ := repo.Create("P", "", []RowInput{
		{Body: "r1", ServerIDs: []string{a}},
		{Body: "r2", ServerIDs: []string{b}},
	}, "")

	got, err := repo.ListByServerIDs([]string{a, b}, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].ID != p.ID {
		t.Errorf("expected single deduped result for multi-row page, got %d", len(got))
	}
}

func TestInstructionRepo_ResolveForToken_FlattensRowsAndFilters(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	for _, s := range []string{a, b} {
		seedServer(t, gdb, s)
	}

	// Page with three rows: r1 → [A, B], r2 → [A] only, r3 → [] (no servers)
	p, _ := repo.Create("P", "", []RowInput{
		{Title: "R1", Body: "b1", ServerIDs: []string{a, b}},
		{Title: "R2", Body: "b2", ServerIDs: []string{a}},
		{Title: "R3", Body: "b3", ServerIDs: nil},
	}, "")

	tokenID := uuid.New().String()
	if err := repo.ReplaceTokenInstructions(tokenID, []string{p.ID}); err != nil {
		t.Fatal(err)
	}

	// Token allowed only on [B]. Expect only R1 (r2 is A-only, r3 unlinked).
	rows, err := repo.ResolveForToken(tokenID, []string{b})
	if err != nil {
		t.Fatalf("ResolveForToken: %v", err)
	}
	if len(rows) != 1 || rows[0].Title != "R1" {
		t.Errorf("expected [R1], got %+v", rowTitles(rows))
	}

	// Token allowed on [A, B] — R1 and R2 appear, R3 excluded.
	rows, err = repo.ResolveForToken(tokenID, []string{a, b})
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 {
		t.Errorf("expected 2 rows for [A,B], got %d: %+v", len(rows), rowTitles(rows))
	}
}

func TestInstructionRepo_ResolveForOAuth2Client(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	seedServer(t, gdb, a)

	p, _ := repo.Create("P", "", []RowInput{{Title: "R", Body: "B", ServerIDs: []string{a}}}, "")

	clientID := uuid.New().String()
	if err := repo.ReplaceOAuth2ClientInstructions(clientID, []string{p.ID}); err != nil {
		t.Fatal(err)
	}

	rows, err := repo.ResolveForOAuth2Client(clientID, []string{a})
	if err != nil {
		t.Fatalf("ResolveForOAuth2Client: %v", err)
	}
	if len(rows) != 1 || rows[0].Title != "R" {
		t.Errorf("expected [R], got %+v", rowTitles(rows))
	}
}

func TestInstructionRepo_ValidateForScope_PageLevel(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	for _, s := range []string{a, b} {
		seedServer(t, gdb, s)
	}

	pAB, _ := repo.Create("pAB", "", []RowInput{{Body: "r", ServerIDs: []string{a, b}}}, "")
	pA, _ := repo.Create("pA", "", []RowInput{{Body: "r", ServerIDs: []string{a}}}, "")

	// allowed=[B]: pAB has a row with B → valid; pA has no row with B → invalid.
	invalid, err := repo.ValidateForScope([]string{pAB.ID, pA.ID}, []string{b})
	if err != nil {
		t.Fatalf("ValidateForScope: %v", err)
	}
	if len(invalid) != 1 || invalid[0] != pA.ID {
		t.Errorf("expected only pA to be invalid, got %v", invalid)
	}

	// allowed=[]: everything is invalid.
	invalid, err = repo.ValidateForScope([]string{pAB.ID}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(invalid) != 1 {
		t.Errorf("empty allowed should invalidate all, got %v", invalid)
	}
}

func TestInstructionRepo_GetUsage(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	seedServer(t, gdb, a)
	p, _ := repo.Create("P", "", []RowInput{{Body: "r", ServerIDs: []string{a}}}, "")

	_ = repo.ReplaceTokenInstructions(uuid.New().String(), []string{p.ID})
	_ = repo.ReplaceTokenInstructions(uuid.New().String(), []string{p.ID})
	_ = repo.ReplaceOAuth2ClientInstructions(uuid.New().String(), []string{p.ID})

	usage, err := repo.GetUsage(p.ID)
	if err != nil {
		t.Fatalf("GetUsage: %v", err)
	}
	if len(usage.TokenIDs) != 2 || len(usage.OAuth2ClientIDs) != 1 {
		t.Errorf("expected 2 tokens / 1 client, got %+v", usage)
	}
}

func TestInstructionRepo_GeneralRowAlwaysResolves(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	for _, s := range []string{a, b} {
		seedServer(t, gdb, s)
	}

	// Page with a general row (no servers) and a per-server row tied to [A].
	p, _ := repo.Create("P", "", []RowInput{
		{Kind: db.LLMInstructionRowKindGeneral, Title: "Global", Body: "Always"},
		{Kind: db.LLMInstructionRowKindPerServer, Title: "A-only", Body: "For A", ServerIDs: []string{a}},
	}, "")

	tokenID := uuid.New().String()
	if err := repo.ReplaceTokenInstructions(tokenID, []string{p.ID}); err != nil {
		t.Fatal(err)
	}

	// Token on [B] — per-server row filtered out, general row survives.
	rows, err := repo.ResolveForToken(tokenID, []string{b})
	if err != nil {
		t.Fatalf("ResolveForToken: %v", err)
	}
	titles := rowTitles(rows)
	if len(rows) != 1 || titles[0] != "Global" {
		t.Errorf("expected only general row for [B], got %v", titles)
	}

	// Token on [A, B] — both rows render.
	rows, err = repo.ResolveForToken(tokenID, []string{a, b})
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 {
		t.Errorf("expected both rows for [A, B], got %d: %v", len(rows), rowTitles(rows))
	}

	// Empty allowed set — still get the general row.
	rows, err = repo.ResolveForToken(tokenID, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 1 || rows[0].Kind != db.LLMInstructionRowKindGeneral {
		t.Errorf("empty allowed should still return general row, got %+v", rowTitles(rows))
	}
}

func TestInstructionRepo_ValidateForScope_GeneralRowPassesAlways(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	seedServer(t, gdb, a)

	pOnlyGen, _ := repo.Create("general-only", "", []RowInput{
		{Kind: db.LLMInstructionRowKindGeneral, Body: "g"},
	}, "")
	pOnlyPerServer, _ := repo.Create("perserver-only", "", []RowInput{
		{Kind: db.LLMInstructionRowKindPerServer, Body: "p", ServerIDs: []string{a}},
	}, "")

	// Empty allowed — only pOnlyGen should pass.
	invalid, err := repo.ValidateForScope([]string{pOnlyGen.ID, pOnlyPerServer.ID}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(invalid) != 1 || invalid[0] != pOnlyPerServer.ID {
		t.Errorf("general-only must be valid with empty allowed, got invalid=%v", invalid)
	}

	// Completely unrelated allowed set — same result, general-only still passes.
	other := uuid.New().String()
	seedServer(t, gdb, other)
	invalid, err = repo.ValidateForScope([]string{pOnlyGen.ID, pOnlyPerServer.ID}, []string{other})
	if err != nil {
		t.Fatal(err)
	}
	if len(invalid) != 1 || invalid[0] != pOnlyPerServer.ID {
		t.Errorf("general-only must be valid regardless of allowed set, got invalid=%v", invalid)
	}
}

func TestInstructionRepo_ListByServerIDs_GeneralRowMakesPageRelevant(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	b := uuid.New().String()
	for _, s := range []string{a, b} {
		seedServer(t, gdb, s)
	}

	pGen, _ := repo.Create("gen", "", []RowInput{
		{Kind: db.LLMInstructionRowKindGeneral, Body: "g"},
	}, "")
	pA, _ := repo.Create("a-only", "", []RowInput{
		{Kind: db.LLMInstructionRowKindPerServer, Body: "p", ServerIDs: []string{a}},
	}, "")

	// Filter [B] — pGen relevant (general), pA not (A-only).
	got, err := repo.ListByServerIDs([]string{b}, "")
	if err != nil {
		t.Fatal(err)
	}
	ids := instructionIDSet(got)
	if !ids[pGen.ID] || ids[pA.ID] {
		t.Errorf("general-only page should match any filter, got %v", ids)
	}
}

func TestInstructionRepo_List_FiltersByCreator(t *testing.T) {
	// Config-only users should see only their own pages. Passing "" disables
	// the filter (admin / background callers).
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	serverA := uuid.New().String()
	seedServer(t, gdb, serverA)

	alice, _ := repo.Create("alice page", "", []RowInput{{Body: "a", ServerIDs: []string{serverA}}}, "alice@example.com")
	bob, _ := repo.Create("bob page", "", []RowInput{{Body: "b", ServerIDs: []string{serverA}}}, "bob@example.com")
	legacy, _ := repo.Create("legacy", "", []RowInput{{Body: "l", ServerIDs: []string{serverA}}}, "")

	// No filter → all three.
	got, err := repo.List("")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 3 {
		t.Errorf("unfiltered list should return all rows, got %d", len(got))
	}

	// Filter as alice → alice's + legacy (legacy has no owner).
	got, err = repo.List("alice@example.com")
	if err != nil {
		t.Fatal(err)
	}
	ids := instructionIDSet(got)
	if !ids[alice.ID] || !ids[legacy.ID] || ids[bob.ID] {
		t.Errorf("alice should see her page + legacy only, got %v", ids)
	}
}

func TestInstructionRepo_ListByServerIDs_FiltersByCreator(t *testing.T) {
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	serverA := uuid.New().String()
	seedServer(t, gdb, serverA)

	_, _ = repo.Create("alice page", "", []RowInput{{Body: "a", ServerIDs: []string{serverA}}}, "alice@example.com")
	bob, _ := repo.Create("bob page", "", []RowInput{{Body: "b", ServerIDs: []string{serverA}}}, "bob@example.com")

	got, err := repo.ListByServerIDs([]string{serverA}, "bob@example.com")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].ID != bob.ID {
		t.Errorf("bob should see only his own page, got %v", instructionIDSet(got))
	}
}

func TestInstructionRepo_GeneralRowIgnoresServerIDsInput(t *testing.T) {
	// Callers sometimes leave stale server IDs on a row whose kind was flipped
	// to "general" — the repo must drop them to keep the junction clean.
	gdb := newInstructionTestDB(t)
	repo := NewInstructionRepo(gdb)
	a := uuid.New().String()
	seedServer(t, gdb, a)

	p, _ := repo.Create("P", "", []RowInput{
		{Kind: db.LLMInstructionRowKindGeneral, Body: "g", ServerIDs: []string{a}},
	}, "")
	got, err := repo.GetByID(p.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Rows) != 1 {
		t.Fatalf("expected 1 row, got %d", len(got.Rows))
	}
	if len(got.Rows[0].Servers) != 0 {
		t.Errorf("general row should have no server links, got %d", len(got.Rows[0].Servers))
	}
}

// ── helpers ───────────────────────────────────────────────────────────────────

func instructionIDSet(ins []db.LLMInstruction) map[string]bool {
	out := make(map[string]bool, len(ins))
	for _, i := range ins {
		out[i.ID] = true
	}
	return out
}

func rowTitles(rows []db.LLMInstructionRow) []string {
	out := make([]string, len(rows))
	for i, r := range rows {
		out[i] = r.Title
	}
	return out
}
