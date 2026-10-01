# Google Templates — Dynamic Secrets + Independent Instance Hosting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a gateway-driven "Templates" feature for Google MCP servers (Google Analytics 4 and Google Search Console, extensible later) where each uploaded service-account JSON spawns an independently-supervised subprocess in a new Python sidecar.

**Architecture:** Control plane (existing `mcp-gateway-service`, Go) stores encrypted credentials and calls a new runtime sidecar (`mcp-google-templates-runner`, Python/FastAPI) that wraps `mcp-proxy` + upstream stdio MCP packages. Each uploaded JSON spawns its own `mcp-proxy` child on a dynamic port (15000–15099). Per-child asyncio supervisor respawns on crash without touching siblings.

**Spec:** [docs/superpowers/specs/2026-04-17-google-templates-dynamic-secrets-design.md](../specs/2026-04-17-google-templates-dynamic-secrets-design.md)

**Tech Stack:** Go 1.24 + GORM + MySQL (gateway), Python 3.11 + FastAPI + asyncio + mcp-proxy + analytics-mcp + mcp-gsc (runner), Vue 3 + Pinia (frontend), Docker.

---

## File Structure

### `apps-microservices/mcp-gateway-service/` (modify existing)

**New:**
- `internal/repository/template_repo.go` — CRUD for templates + template_instances, encryption
- `internal/repository/template_repo_test.go`
- `internal/api/template_handlers.go` — REST endpoints
- `internal/api/template_handlers_test.go`
- `internal/api/template_dto.go` — request/response DTOs
- `internal/api/internal_handlers.go` — `POST /api/v1/internal/runner/sync`
- `internal/runnerclient/client.go` — HTTP client for runner admin API
- `internal/runnerclient/client_test.go`
- `internal/runnerclient/types.go` — request/response types
- `internal/validation/saJson.go` — SA JSON validator
- `internal/validation/saJson_test.go`

**Modify:**
- `internal/db/models.go` — add `Template` and `TemplateInstance` structs
- `internal/db/mysql.go` — register the two new models in `AutoMigrate`
- `internal/db/mysql_test.go` — add `TableName` assertions for both
- `internal/config/config.go` — add `GoogleTemplatesRunnerURL`, `GoogleTemplatesRunnerAdminToken`
- `internal/api/handler.go` — add repos/client to `Handler`, register routes
- `cmd/server/main.go` — wire up template repo + runner client
- `init-db/init-mcp-gateway-db.sql` — seed `templates` table
- `CLAUDE.md` — document new env vars + tables + endpoints

### `apps-microservices/mcp-google-templates-runner/` (new service)

```
mcp-google-templates-runner/
  app/
    main.py                  # FastAPI app + lifespan
    config.py                # Pydantic BaseSettings
    auth.py                  # X-Admin-Token dependency
    supervisor.py            # per-instance asyncio supervisor
    port_pool.py             # port allocator
    credentials.py           # tmpfs write/shred
    gateway_sync.py          # startup sync call to gateway
    api/
      admin.py               # /admin/* endpoints
    models.py                # pydantic schemas for admin API
  tests/
    test_supervisor.py
    test_port_pool.py
    test_credentials.py
    test_admin_api.py
  requirements.txt
  Dockerfile
  entrypoint.sh
  CLAUDE.md
```

### `apps-microservices/mcp-gateway-frontend/` (modify existing)

**New:**
- `src/api/templates.ts`
- `src/stores/templates.ts`
- `src/views/TemplatesView.vue`
- `src/views/TemplateDetailView.vue`
- `src/components/templates/TemplateInstanceCard.vue`
- `src/components/templates/AddInstanceModal.vue`
- `src/components/templates/RotateCredentialsModal.vue`
- `src/components/templates/InstanceLogsModal.vue`

**Modify:**
- `src/router/index.ts` — add `/admin/templates` + `/admin/templates/:slug` routes
- `src/components/NavBar.vue` (or the equivalent main nav file) — add Templates tab
- `src/types/` — add template types

### Root

**Modify:**
- `docker-compose.yml` — add `mcp-google-templates-runner` service with tmpfs mount
- `CLAUDE.md` — add runner to service map
- `.env.example` — add new env vars

---

## Phase 0 — Setup

### Task 0: Create feature branch

- [ ] **Step 1: Confirm you are on `features/poc`**

Run: `git rev-parse --abbrev-ref HEAD`
Expected: `features/poc`

- [ ] **Step 2: Pull latest and create feature branch**

Run: `git pull origin features/poc && git checkout -b features/google-templates`

- [ ] **Step 3: Verify the spec is the latest**

Run: `git log --oneline -3 -- docs/superpowers/specs/2026-04-17-google-templates-dynamic-secrets-design.md`
Expected: top commit is `7283dcc7 docs(mcp-gateway): shift runner port pool to 15000-15099`

---

## Phase 1 — Gateway: Data model

### Task 1: Add Template + TemplateInstance GORM models

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/db/models.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/db/mysql.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/db/mysql_test.go`

- [ ] **Step 1: Write the failing test**

Append to `internal/db/mysql_test.go` inside the `tests` slice:

```go
{Template{}, "templates"},
{TemplateInstance{}, "template_instances"},
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/mcp-gateway-service && go test ./internal/db/...`
Expected: FAIL — `Template` / `TemplateInstance` undefined

- [ ] **Step 3: Add the two structs at the bottom of `internal/db/models.go`**

```go
// Template is the GORM model for the templates catalog (seed data).
// Rows are managed via migration, never via user input.
type Template struct {
	Slug             string          `gorm:"type:varchar(32);primaryKey" json:"slug"`
	Name             string          `gorm:"type:varchar(128);not null" json:"name"`
	Description      string          `gorm:"type:text" json:"description"`
	Icon             string          `gorm:"type:varchar(512);not null;default:''" json:"icon"`
	StdioCommand     string          `gorm:"type:varchar(256);not null" json:"stdio_command"`
	StdioArgs        json.RawMessage `gorm:"type:json" json:"stdio_args"`
	DefaultEnv       json.RawMessage `gorm:"type:json" json:"default_env"`
	RequiredExtraEnv json.RawMessage `gorm:"type:json" json:"required_extra_env"`
	ToolPrefix       string          `gorm:"type:varchar(64);not null;default:''" json:"tool_prefix"`
	Tags             json.RawMessage `gorm:"type:json" json:"tags"`
	IsActive         bool            `gorm:"not null;default:true;index:idx_template_active" json:"is_active"`
	CreatedAt        time.Time       `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt        time.Time       `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (Template) TableName() string { return "templates" }

// TemplateInstance is one admin-uploaded service-account JSON. Each row backs
// exactly one running mcp-proxy subprocess in the runner.
type TemplateInstance struct {
	ID                   string     `gorm:"type:char(36);primaryKey" json:"id"`
	TemplateSlug         string     `gorm:"type:varchar(32);not null;index:idx_instance_template" json:"template_slug"`
	Name                 string     `gorm:"type:varchar(255);not null" json:"name"`
	EncryptedCredentials []byte     `gorm:"type:blob;not null" json:"-"`
	CredentialsHash      string     `gorm:"type:char(64);not null" json:"-"`
	ExtraEnv             json.RawMessage `gorm:"type:json" json:"extra_env,omitempty"`
	RunnerPort           *int       `gorm:"type:int" json:"runner_port,omitempty"`
	RunnerStatus         string     `gorm:"type:varchar(16);not null;default:'pending';index:idx_instance_status" json:"runner_status"`
	RunnerLastError      string     `gorm:"type:text" json:"runner_last_error,omitempty"`
	MCPServerID          string     `gorm:"type:char(36);not null;uniqueIndex:uq_instance_mcp_server" json:"mcp_server_id"`
	CreatedBy            string     `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	CreatedAt            time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt            time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (TemplateInstance) TableName() string { return "template_instances" }
```

- [ ] **Step 4: Register models in `AutoMigrate`**

In `internal/db/mysql.go`, append to the `db.AutoMigrate(...)` call (keep alphabetical of similar items, add near the end of the slice):

```go
&Template{},
&TemplateInstance{},
```

- [ ] **Step 5: Run tests to verify pass**

Run: `go test ./internal/db/...`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add internal/db/
git commit -m "feat(mcp-gateway): add Template + TemplateInstance GORM models"
```

---

## Phase 2 — Gateway: SA JSON validation

### Task 2: Service-account JSON validator

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/validation/saJson.go`
- Create: `apps-microservices/mcp-gateway-service/internal/validation/saJson_test.go`

- [ ] **Step 1: Write the failing test**

Create `internal/validation/saJson_test.go`:

```go
package validation

import (
	"strings"
	"testing"
)

const validSA = `{
  "type": "service_account",
  "project_id": "my-project",
  "client_email": "bot@my-project.iam.gserviceaccount.com",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
}`

func TestValidateServiceAccountJSON_OK(t *testing.T) {
	info, err := ValidateServiceAccountJSON([]byte(validSA))
	if err != nil {
		t.Fatalf("want nil err, got %v", err)
	}
	if info.ClientEmail != "bot@my-project.iam.gserviceaccount.com" {
		t.Errorf("ClientEmail = %q", info.ClientEmail)
	}
	if info.ProjectID != "my-project" {
		t.Errorf("ProjectID = %q", info.ProjectID)
	}
}

func TestValidateServiceAccountJSON_Errors(t *testing.T) {
	cases := []struct {
		name   string
		input  string
		errSub string
	}{
		{"empty", ``, "parse"},
		{"bad type", strings.Replace(validSA, `"service_account"`, `"user"`, 1), "type must be service_account"},
		{"no email", strings.Replace(validSA, `"client_email": "bot@my-project.iam.gserviceaccount.com",`, ``, 1), "client_email"},
		{"no project", strings.Replace(validSA, `"project_id": "my-project",`, ``, 1), "project_id"},
		{"no private_key", strings.Replace(validSA, `"private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"`, `"private_key": ""`, 1), "private_key"},
		{"wrong PK format", strings.Replace(validSA, `-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n`, `not-a-pem`, 1), "private_key"},
		{"too big", `{"type":"service_account"` + strings.Repeat(" ", 17*1024) + `}`, "too large"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ValidateServiceAccountJSON([]byte(tc.input))
			if err == nil {
				t.Fatalf("want error")
			}
			if !strings.Contains(err.Error(), tc.errSub) {
				t.Errorf("err = %v, want substring %q", err, tc.errSub)
			}
		})
	}
}
```

- [ ] **Step 2: Run test, confirm fails**

Run: `go test ./internal/validation/...`
Expected: FAIL — `ValidateServiceAccountJSON` undefined

- [ ] **Step 3: Implement `internal/validation/saJson.go`**

```go
// Package validation — SA JSON validation before encrypt/store.
package validation

import (
	"encoding/json"
	"fmt"
	"strings"
)

const MaxSAJSONSize = 16 * 1024 // 16 KB; real SA JSONs are ~2 KB

type ServiceAccountInfo struct {
	Type        string `json:"type"`
	ProjectID   string `json:"project_id"`
	ClientEmail string `json:"client_email"`
	PrivateKey  string `json:"private_key"`
}

func ValidateServiceAccountJSON(raw []byte) (*ServiceAccountInfo, error) {
	if len(raw) > MaxSAJSONSize {
		return nil, fmt.Errorf("file too large: %d bytes (max %d)", len(raw), MaxSAJSONSize)
	}
	var info ServiceAccountInfo
	if err := json.Unmarshal(raw, &info); err != nil {
		return nil, fmt.Errorf("parse JSON: %w", err)
	}
	if info.Type != "service_account" {
		return nil, fmt.Errorf("type must be service_account, got %q", info.Type)
	}
	if info.ProjectID == "" {
		return nil, fmt.Errorf("project_id is required")
	}
	if info.ClientEmail == "" {
		return nil, fmt.Errorf("client_email is required")
	}
	if !strings.Contains(info.ClientEmail, ".iam.gserviceaccount.com") &&
		!strings.HasSuffix(info.ClientEmail, "@appspot.gserviceaccount.com") {
		return nil, fmt.Errorf("client_email does not look like a service account email")
	}
	if info.PrivateKey == "" {
		return nil, fmt.Errorf("private_key is required")
	}
	if !strings.HasPrefix(strings.TrimSpace(info.PrivateKey), "-----BEGIN PRIVATE KEY-----") {
		return nil, fmt.Errorf("private_key must be PEM-encoded (starts with -----BEGIN PRIVATE KEY-----)")
	}
	return &info, nil
}
```

- [ ] **Step 4: Run test, verify pass**

Run: `go test ./internal/validation/...`
Expected: PASS, all cases

- [ ] **Step 5: Commit**

```bash
git add internal/validation/
git commit -m "feat(mcp-gateway): add SA JSON validator for template uploads"
```

---

## Phase 3 — Gateway: Repository layer

### Task 3: TemplateRepo (list/get for catalog)

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/repository/template_repo.go`
- Create: `apps-microservices/mcp-gateway-service/internal/repository/template_repo_test.go`

- [ ] **Step 1: Write the failing test**

Create `internal/repository/template_repo_test.go` — mirrors the pattern of `server_repo_test.go` (use sqlite-in-memory if that's the convention, else skip if no test DB; grep `server_repo_test.go` first for the exact pattern):

```go
package repository

import (
	"encoding/json"
	"testing"

	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

func newTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := gdb.AutoMigrate(&db.MCPServer{}, &db.Template{}, &db.TemplateInstance{}); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return gdb
}

func TestTemplateRepo_ListActive(t *testing.T) {
	gdb := newTestDB(t)
	gdb.Create(&db.Template{Slug: "ga", Name: "GA4", StdioCommand: "analytics-mcp", IsActive: true, Tags: json.RawMessage(`["google"]`)})
	gdb.Create(&db.Template{Slug: "gsc", Name: "GSC", StdioCommand: "mcp-gsc", IsActive: true})
	gdb.Create(&db.Template{Slug: "old", Name: "Old", StdioCommand: "x", IsActive: false})

	repo := NewTemplateRepo(gdb)
	out, err := repo.ListActive()
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(out) != 2 {
		t.Errorf("want 2, got %d", len(out))
	}
}

func TestTemplateRepo_GetBySlug_NotFound(t *testing.T) {
	gdb := newTestDB(t)
	repo := NewTemplateRepo(gdb)
	_, err := repo.GetBySlug("nope")
	if err == nil {
		t.Fatal("want error")
	}
}
```

- [ ] **Step 2: Run test, verify fails (NewTemplateRepo undefined)**

Run: `go test ./internal/repository/... -run TestTemplate -v`
Expected: FAIL

- [ ] **Step 3: Implement `internal/repository/template_repo.go`**

```go
package repository

import (
	"github.com/hellopro/mcp-gateway/internal/db"
	"gorm.io/gorm"
)

type TemplateRepo struct {
	db *gorm.DB
}

func NewTemplateRepo(database *gorm.DB) *TemplateRepo {
	return &TemplateRepo{db: database}
}

func (r *TemplateRepo) ListActive() ([]db.Template, error) {
	var out []db.Template
	err := r.db.Where("is_active = ?", true).Order("name ASC").Find(&out).Error
	return out, err
}

func (r *TemplateRepo) GetBySlug(slug string) (*db.Template, error) {
	var t db.Template
	if err := r.db.First(&t, "slug = ? AND is_active = ?", slug, true).Error; err != nil {
		return nil, err
	}
	return &t, nil
}
```

- [ ] **Step 4: Run test, verify pass**

Run: `go test ./internal/repository/... -run TestTemplate -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/repository/template_repo.go internal/repository/template_repo_test.go
git commit -m "feat(mcp-gateway): add TemplateRepo for template catalog"
```

### Task 4: InstanceRepo (CRUD + encryption + transactional delete)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/repository/template_repo.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/repository/template_repo_test.go`

- [ ] **Step 1: Write failing tests for the instance CRUD**

Append to `template_repo_test.go`:

```go
import (
	"crypto/sha256"
	"encoding/hex"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/crypto"
)

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
	gdb := newTestDB(t)
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
}
```

- [ ] **Step 2: Run, verify fails**

Run: `go test ./internal/repository/... -run TestInstanceRepo -v`
Expected: FAIL (`NewInstanceRepo` undefined)

- [ ] **Step 3: Implement**

Append to `template_repo.go`:

```go
import (
	"fmt"
	"github.com/hellopro/mcp-gateway/internal/crypto"
)

type InstanceRepo struct {
	db        *gorm.DB
	encryptor *crypto.Encryptor // must be non-nil (encryption is mandatory here)
}

func NewInstanceRepo(database *gorm.DB, encryptor *crypto.Encryptor) *InstanceRepo {
	return &InstanceRepo{db: database, encryptor: encryptor}
}

func (r *InstanceRepo) Create(inst *db.TemplateInstance, credentialsPlain []byte) error {
	if r.encryptor == nil {
		return fmt.Errorf("encryptor required for template instances")
	}
	ct, err := r.encryptor.Encrypt(credentialsPlain)
	if err != nil {
		return fmt.Errorf("encrypt credentials: %w", err)
	}
	inst.EncryptedCredentials = ct
	return r.db.Create(inst).Error
}

func (r *InstanceRepo) GetByIDWithCredentials(id string) (*db.TemplateInstance, []byte, error) {
	var inst db.TemplateInstance
	if err := r.db.First(&inst, "id = ?", id).Error; err != nil {
		return nil, nil, err
	}
	plain, err := r.encryptor.Decrypt(inst.EncryptedCredentials)
	if err != nil {
		return nil, nil, fmt.Errorf("decrypt: %w", err)
	}
	return &inst, plain, nil
}

func (r *InstanceRepo) GetByID(id string) (*db.TemplateInstance, error) {
	var inst db.TemplateInstance
	if err := r.db.First(&inst, "id = ?", id).Error; err != nil {
		return nil, err
	}
	return &inst, nil
}

func (r *InstanceRepo) ListAll() ([]db.TemplateInstance, error) {
	var out []db.TemplateInstance
	err := r.db.Order("created_at DESC").Find(&out).Error
	return out, err
}

func (r *InstanceRepo) ListByTemplate(slug string) ([]db.TemplateInstance, error) {
	var out []db.TemplateInstance
	err := r.db.Where("template_slug = ?", slug).Order("created_at DESC").Find(&out).Error
	return out, err
}

func (r *InstanceRepo) UpdateStatus(id, status, lastError string, port *int) error {
	updates := map[string]any{
		"runner_status":     status,
		"runner_last_error": lastError,
	}
	if port != nil {
		updates["runner_port"] = *port
	}
	return r.db.Model(&db.TemplateInstance{}).Where("id = ?", id).Updates(updates).Error
}

func (r *InstanceRepo) UpdateCredentials(id string, credentialsPlain []byte, hashHex string) error {
	ct, err := r.encryptor.Encrypt(credentialsPlain)
	if err != nil {
		return fmt.Errorf("encrypt: %w", err)
	}
	return r.db.Model(&db.TemplateInstance{}).Where("id = ?", id).Updates(map[string]any{
		"encrypted_credentials": ct,
		"credentials_hash":      hashHex,
	}).Error
}

// DeleteWithMCPServer removes both the instance row and its linked mcp_servers
// row in a single transaction. Cascade on mcp_servers covers tools, resources,
// prompts, tags, and scope/oauth2 join tables.
func (r *InstanceRepo) DeleteWithMCPServer(id string) error {
	return r.db.Transaction(func(tx *gorm.DB) error {
		var inst db.TemplateInstance
		if err := tx.First(&inst, "id = ?", id).Error; err != nil {
			return err
		}
		if err := tx.Delete(&inst).Error; err != nil {
			return err
		}
		return tx.Delete(&db.MCPServer{}, "id = ?", inst.MCPServerID).Error
	})
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `go test ./internal/repository/... -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/repository/
git commit -m "feat(mcp-gateway): add InstanceRepo with encrypted credentials + transactional delete"
```

---

## Phase 4 — Gateway: Config

### Task 5: Add runner URL + admin token env vars

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/config/config.go`

- [ ] **Step 1: Add fields to `Config` struct**

Append to the `Config` struct in `config.go` (after the Leexi block):

```go
// Google templates runner (mcp-google-templates-runner sidecar).
GoogleTemplatesRunnerURL        string // GOOGLE_TEMPLATES_RUNNER_URL
GoogleTemplatesRunnerAdminToken string // GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN
```

- [ ] **Step 2: Read them in `Load()`**

In the `return &Config{...}` block, add:

```go
GoogleTemplatesRunnerURL:        os.Getenv("GOOGLE_TEMPLATES_RUNNER_URL"),
GoogleTemplatesRunnerAdminToken: os.Getenv("GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN"),
```

- [ ] **Step 3: Build check**

Run: `go build ./...`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add internal/config/config.go
git commit -m "feat(mcp-gateway): add runner URL + admin token config"
```

---

## Phase 5 — Gateway: Runner client

### Task 6: HTTP client for runner admin API

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/runnerclient/types.go`
- Create: `apps-microservices/mcp-gateway-service/internal/runnerclient/client.go`
- Create: `apps-microservices/mcp-gateway-service/internal/runnerclient/client_test.go`

- [ ] **Step 1: Write types**

Create `types.go`:

```go
package runnerclient

// SpawnRequest is sent to POST /admin/instances.
type SpawnRequest struct {
	InstanceID       string            `json:"instance_id"`
	TemplateSlug     string            `json:"template_slug"`
	StdioCommand     string            `json:"stdio_command"`
	StdioArgs        []string          `json:"stdio_args"`
	Env              map[string]string `json:"env"`
	CredentialsJSON  string            `json:"credentials_json"` // raw SA JSON
	CredentialsHash  string            `json:"credentials_hash"` // sha256 hex
}

type SpawnResponse struct {
	Port int `json:"port"`
	PID  int `json:"pid"`
}

type InstanceStatus struct {
	ID         string `json:"id"`
	Port       int    `json:"port"`
	PID        int    `json:"pid"`
	Status     string `json:"status"` // pending | running | failed | stopped
	UptimeSec  int    `json:"uptime_s"`
	LastError  string `json:"last_error,omitempty"`
	StderrTail string `json:"stderr_tail,omitempty"`
}

type ReconcileRequest struct {
	DesiredInstances []SpawnRequest `json:"desired_instances"`
}
```

- [ ] **Step 2: Write failing test**

Create `client_test.go`:

```go
package runnerclient

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSpawn_OK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Admin-Token") != "t" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		if r.Method != http.MethodPost || r.URL.Path != "/admin/instances" {
			http.NotFound(w, r)
			return
		}
		_ = json.NewEncoder(w).Encode(SpawnResponse{Port: 15000, PID: 42})
	}))
	defer srv.Close()

	c := New(srv.URL, "t")
	out, err := c.Spawn(SpawnRequest{InstanceID: "x", TemplateSlug: "ga", StdioCommand: "analytics-mcp"})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if out.Port != 15000 || out.PID != 42 {
		t.Errorf("got %+v", out)
	}
}

func TestSpawn_BadToken(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer srv.Close()

	c := New(srv.URL, "wrong")
	_, err := c.Spawn(SpawnRequest{InstanceID: "x"})
	if err == nil {
		t.Fatal("want error")
	}
}
```

- [ ] **Step 3: Run, verify fails**

Run: `go test ./internal/runnerclient/... -v`
Expected: FAIL (`New` / `Spawn` undefined)

- [ ] **Step 4: Implement client**

Create `client.go`:

```go
package runnerclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Client struct {
	baseURL    string
	adminToken string
	http       *http.Client
}

func New(baseURL, adminToken string) *Client {
	return &Client{
		baseURL:    baseURL,
		adminToken: adminToken,
		http:       &http.Client{Timeout: 15 * time.Second},
	}
}

func (c *Client) do(ctx context.Context, method, path string, body any, out any) error {
	var reader *bytes.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encode: %w", err)
		}
		reader = bytes.NewReader(b)
	}
	var req *http.Request
	var err error
	if reader != nil {
		req, err = http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	} else {
		req, err = http.NewRequestWithContext(ctx, method, c.baseURL+path, nil)
	}
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-Token", c.adminToken)

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("runner %s %s: %w", method, path, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errBody map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&errBody)
		return fmt.Errorf("runner %s %s: status %d: %v", method, path, resp.StatusCode, errBody)
	}
	if out != nil {
		return json.NewDecoder(resp.Body).Decode(out)
	}
	return nil
}

func (c *Client) Spawn(req SpawnRequest) (*SpawnResponse, error) {
	var out SpawnResponse
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := c.do(ctx, http.MethodPost, "/admin/instances", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) Kill(instanceID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return c.do(ctx, http.MethodDelete, "/admin/instances/"+instanceID, nil, nil)
}

func (c *Client) Restart(instanceID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return c.do(ctx, http.MethodPost, "/admin/instances/"+instanceID+"/restart", nil, nil)
}

func (c *Client) List() ([]InstanceStatus, error) {
	var out struct {
		Instances []InstanceStatus `json:"instances"`
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := c.do(ctx, http.MethodGet, "/admin/instances", nil, &out); err != nil {
		return nil, err
	}
	return out.Instances, nil
}

func (c *Client) Reconcile(desired []SpawnRequest) error {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	return c.do(ctx, http.MethodPost, "/admin/reconcile", ReconcileRequest{DesiredInstances: desired}, nil)
}
```

- [ ] **Step 5: Run tests, verify pass**

Run: `go test ./internal/runnerclient/... -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add internal/runnerclient/
git commit -m "feat(mcp-gateway): add HTTP client for runner admin API"
```

---

## Phase 6 — Gateway: API DTOs + handlers

### Task 7: Template DTOs + list/get handlers

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/api/template_dto.go`
- Create: `apps-microservices/mcp-gateway-service/internal/api/template_handlers.go`

- [ ] **Step 1: Write DTOs**

Create `template_dto.go`:

```go
package api

import (
	"encoding/json"
	"time"
)

type TemplateResponse struct {
	Slug             string          `json:"slug"`
	Name             string          `json:"name"`
	Description      string          `json:"description"`
	Icon             string          `json:"icon"`
	StdioCommand     string          `json:"stdio_command"`
	StdioArgs        json.RawMessage `json:"stdio_args"`
	DefaultEnv       json.RawMessage `json:"default_env"`
	RequiredExtraEnv json.RawMessage `json:"required_extra_env"`
	ToolPrefix       string          `json:"tool_prefix"`
	Tags             json.RawMessage `json:"tags"`
	InstanceCount    int             `json:"instance_count"`
}

type TemplateInstanceResponse struct {
	ID              string          `json:"id"`
	TemplateSlug    string          `json:"template_slug"`
	Name            string          `json:"name"`
	ExtraEnv        json.RawMessage `json:"extra_env,omitempty"`
	RunnerPort      *int            `json:"runner_port,omitempty"`
	RunnerStatus    string          `json:"runner_status"`
	RunnerLastError string          `json:"runner_last_error,omitempty"`
	MCPServerID     string          `json:"mcp_server_id"`
	CreatedBy       string          `json:"created_by"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`
	// Filled by GetByID only:
	StderrTail      string          `json:"stderr_tail,omitempty"`
}

type CreateInstanceRequest struct {
	TemplateSlug string            `json:"template_slug"`
	Name         string            `json:"name"`
	ExtraEnv     map[string]string `json:"extra_env,omitempty"`
	// Credentials come via multipart file part "credentials", not JSON body.
}
```

- [ ] **Step 2: Write failing test** (`template_handlers_test.go`) — one for `GET /templates`, one for `GET /templates/{slug}` not-found. Mirror pattern from existing `server_handlers` tests. (Code below is an excerpt.)

```go
package api

// See existing server_handlers_test.go for the full bootstrap — inject the
// same handler, sqlite-in-memory, seed two templates, assert JSON.
```

- [ ] **Step 3: Implement the two handlers in `template_handlers.go`**

```go
package api

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/db"
)

func (h *Handler) handleListTemplates(w http.ResponseWriter, r *http.Request) {
	templates, err := h.templateRepo.ListActive()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "list templates: " + err.Error()})
		return
	}
	counts, err := h.instanceRepo.CountsByTemplate()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "count: " + err.Error()})
		return
	}
	out := make([]TemplateResponse, 0, len(templates))
	for _, t := range templates {
		out = append(out, toTemplateResponse(t, counts[t.Slug]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"templates": out})
}

func (h *Handler) handleGetTemplate(w http.ResponseWriter, r *http.Request) {
	slug := strings.TrimPrefix(r.URL.Path, "/api/v1/templates/")
	if slug == "" || strings.Contains(slug, "/") {
		http.NotFound(w, r)
		return
	}
	t, err := h.templateRepo.GetBySlug(slug)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "template not found"})
		return
	}
	counts, _ := h.instanceRepo.CountsByTemplate()
	writeJSON(w, http.StatusOK, toTemplateResponse(*t, counts[t.Slug]))
}

func toTemplateResponse(t db.Template, count int) TemplateResponse {
	return TemplateResponse{
		Slug: t.Slug, Name: t.Name, Description: t.Description, Icon: t.Icon,
		StdioCommand: t.StdioCommand, StdioArgs: t.StdioArgs,
		DefaultEnv: t.DefaultEnv, RequiredExtraEnv: t.RequiredExtraEnv,
		ToolPrefix: t.ToolPrefix, Tags: t.Tags, InstanceCount: count,
	}
}
```

- [ ] **Step 4: Add `CountsByTemplate` to `InstanceRepo`**

In `template_repo.go`:

```go
func (r *InstanceRepo) CountsByTemplate() (map[string]int, error) {
	var rows []struct {
		TemplateSlug string
		Cnt          int
	}
	err := r.db.Model(&db.TemplateInstance{}).
		Select("template_slug, COUNT(*) as cnt").
		Group("template_slug").
		Scan(&rows).Error
	if err != nil {
		return nil, err
	}
	m := make(map[string]int, len(rows))
	for _, row := range rows {
		m[row.TemplateSlug] = row.Cnt
	}
	return m, nil
}
```

- [ ] **Step 5: Add `templateRepo` + `instanceRepo` + `runnerClient` to the `Handler` struct**

In `internal/api/server_handlers.go` (the `Handler` struct, around lines 65–80), add:

```go
templateRepo *repository.TemplateRepo
instanceRepo *repository.InstanceRepo
runner       *runnerclient.Client
```

- [ ] **Step 6: Build**

Run: `go build ./...`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add internal/api/template_dto.go internal/api/template_handlers.go internal/api/server_handlers.go internal/repository/template_repo.go
git commit -m "feat(mcp-gateway): add GET /templates list + detail handlers"
```

### Task 8: GET /template-instances list + detail

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/template_handlers.go`

- [ ] **Step 1: Add list handler**

```go
func (h *Handler) handleListInstances(w http.ResponseWriter, r *http.Request) {
	slug := r.URL.Query().Get("template_slug")
	var instances []db.TemplateInstance
	var err error
	if slug != "" {
		instances, err = h.instanceRepo.ListByTemplate(slug)
	} else {
		instances, err = h.instanceRepo.ListAll()
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	out := make([]TemplateInstanceResponse, 0, len(instances))
	for _, inst := range instances {
		out = append(out, toInstanceResponse(inst, ""))
	}
	writeJSON(w, http.StatusOK, map[string]any{"instances": out})
}

func (h *Handler) handleGetInstance(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/api/v1/template-instances/")
	id = strings.TrimSuffix(id, "/")
	if id == "" || strings.Contains(id, "/") {
		http.NotFound(w, r)
		return
	}
	inst, err := h.instanceRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
		return
	}
	// Live stderr tail from runner
	tail := ""
	if h.runner != nil {
		if statuses, err := h.runner.List(); err == nil {
			for _, s := range statuses {
				if s.ID == id {
					tail = s.StderrTail
					break
				}
			}
		}
	}
	writeJSON(w, http.StatusOK, toInstanceResponse(*inst, tail))
}

func toInstanceResponse(inst db.TemplateInstance, stderrTail string) TemplateInstanceResponse {
	return TemplateInstanceResponse{
		ID: inst.ID, TemplateSlug: inst.TemplateSlug, Name: inst.Name,
		ExtraEnv: inst.ExtraEnv, RunnerPort: inst.RunnerPort,
		RunnerStatus: inst.RunnerStatus, RunnerLastError: inst.RunnerLastError,
		MCPServerID: inst.MCPServerID, CreatedBy: inst.CreatedBy,
		CreatedAt: inst.CreatedAt, UpdatedAt: inst.UpdatedAt,
		StderrTail: stderrTail,
	}
}
```

- [ ] **Step 2: Build**

Run: `go build ./...`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add internal/api/template_handlers.go
git commit -m "feat(mcp-gateway): add GET /template-instances list + detail"
```

### Task 9: POST /template-instances (upload + validate + encrypt + spawn + create mcp_servers)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/template_handlers.go`

This is the load-bearing handler.

- [ ] **Step 1: Implement `handleCreateInstance`**

```go
func (h *Handler) handleCreateInstance(w http.ResponseWriter, r *http.Request) {
	// Multipart: fields "template_slug", "name", "extra_env" (JSON string), file "credentials"
	if err := r.ParseMultipartForm(validation.MaxSAJSONSize + 16*1024); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "multipart parse: " + err.Error()})
		return
	}

	slug := r.FormValue("template_slug")
	name := strings.TrimSpace(r.FormValue("name"))
	if slug == "" || name == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "template_slug and name required"})
		return
	}
	tpl, err := h.templateRepo.GetBySlug(slug)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "unknown template: " + slug})
		return
	}

	// Parse extra_env
	var extraEnv map[string]string
	if raw := r.FormValue("extra_env"); raw != "" {
		if err := json.Unmarshal([]byte(raw), &extraEnv); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "extra_env: invalid JSON"})
			return
		}
	}
	// Validate extra_env against template's required_extra_env
	if err := validateExtraEnv(tpl.RequiredExtraEnv, extraEnv); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}

	// Read credentials file
	file, hdr, err := r.FormFile("credentials")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing credentials file"})
		return
	}
	defer file.Close()
	if hdr.Size > int64(validation.MaxSAJSONSize) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "credentials file too large"})
		return
	}
	credBytes, err := io.ReadAll(io.LimitReader(file, int64(validation.MaxSAJSONSize)+1))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "read credentials: " + err.Error()})
		return
	}
	saInfo, err := validation.ValidateServiceAccountJSON(credBytes)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid credentials: " + err.Error()})
		return
	}

	// Generate ids, hash
	instanceID := uuid.New().String()
	mcpServerID := instanceID // per spec: reuse the same UUID
	hash := sha256.Sum256(credBytes)
	hashHex := hex.EncodeToString(hash[:])

	// Compute env (default_env + extra_env), substituting {instance_id}
	env := renderEnv(tpl.DefaultEnv, extraEnv, instanceID)

	// Decode stdio_args
	var stdioArgs []string
	if len(tpl.StdioArgs) > 0 {
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
	}

	// 1) Insert mcp_servers row (placeholder URL — runner returns port)
	mcpSrv := db.MCPServer{
		ID:                  mcpServerID,
		Name:                tpl.Name + " — " + name,
		URL:                 "http://pending",
		MCPTransport:        "http",
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		ToolPrefix:          tpl.ToolPrefix,
		DocSlug:             generateDocSlug(tpl.Name+"-"+name, mcpServerID),
		CreatedBy:           auth.UserEmailFromContext(r.Context()),
	}
	if err := h.repo.Create(&mcpSrv); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create mcp_server: " + err.Error()})
		return
	}

	// 2) Insert template_instances row (encrypts credentials)
	extraEnvJSON, _ := json.Marshal(extraEnv)
	inst := db.TemplateInstance{
		ID: instanceID, TemplateSlug: slug, Name: name,
		CredentialsHash: hashHex, ExtraEnv: extraEnvJSON,
		RunnerStatus: "pending", MCPServerID: mcpServerID,
		CreatedBy: auth.UserEmailFromContext(r.Context()),
	}
	if err := h.instanceRepo.Create(&inst, credBytes); err != nil {
		_ = h.repo.Delete(mcpServerID) // rollback
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create instance: " + err.Error()})
		return
	}

	// 3) Call runner to spawn
	resp, err := h.runner.Spawn(runnerclient.SpawnRequest{
		InstanceID: instanceID, TemplateSlug: slug,
		StdioCommand: tpl.StdioCommand, StdioArgs: stdioArgs,
		Env: env, CredentialsJSON: string(credBytes), CredentialsHash: hashHex,
	})
	if err != nil {
		_ = h.instanceRepo.UpdateStatus(instanceID, "failed", err.Error(), nil)
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner spawn failed: " + err.Error()})
		return
	}

	// 4) Update mcp_servers URL + instance port
	runnerHost := strings.TrimPrefix(strings.TrimPrefix(h.config.GoogleTemplatesRunnerURL, "http://"), "https://")
	runnerHost = strings.SplitN(runnerHost, ":", 2)[0]
	instanceURL := fmt.Sprintf("http://%s:%d", runnerHost, resp.Port)
	if err := h.repo.UpdateURL(mcpServerID, instanceURL); err != nil {
		log.Printf("[templates] warn: could not update mcp_server URL: %v", err)
	}
	port := resp.Port
	_ = h.instanceRepo.UpdateStatus(instanceID, "running", "", &port)

	// 5) Return 201 — use the info from SA JSON for the client_email field
	_ = saInfo // already validated; client_email available if we want to return it
	inst.RunnerPort = &port
	inst.RunnerStatus = "running"
	writeJSON(w, http.StatusCreated, toInstanceResponse(inst, ""))
}
```

- [ ] **Step 2: Add `renderEnv` + `validateExtraEnv` helpers at the bottom of the file**

```go
// renderEnv merges default_env (from template) + extra_env (admin input),
// substituting {instance_id} in default_env values.
func renderEnv(defaultEnvRaw json.RawMessage, extra map[string]string, instanceID string) map[string]string {
	out := make(map[string]string)
	var def map[string]string
	if len(defaultEnvRaw) > 0 {
		_ = json.Unmarshal(defaultEnvRaw, &def)
	}
	for k, v := range def {
		out[k] = strings.ReplaceAll(v, "{instance_id}", instanceID)
	}
	for k, v := range extra {
		out[k] = v
	}
	return out
}

// validateExtraEnv checks that admin-supplied extra_env matches the template's schema.
func validateExtraEnv(schemaRaw json.RawMessage, extra map[string]string) error {
	if len(schemaRaw) == 0 {
		return nil
	}
	var schema []struct {
		Key      string `json:"key"`
		Required bool   `json:"required"`
	}
	if err := json.Unmarshal(schemaRaw, &schema); err != nil {
		return nil // best-effort — if schema is malformed, skip
	}
	for _, field := range schema {
		if field.Required {
			if v, ok := extra[field.Key]; !ok || v == "" {
				return fmt.Errorf("extra_env: %q is required", field.Key)
			}
		}
	}
	return nil
}
```

- [ ] **Step 3: Add `UpdateURL` method to `ServerRepo`** (file `internal/repository/server_repo.go`)

Append:

```go
func (r *ServerRepo) UpdateURL(id, url string) error {
	return r.db.Model(&db.MCPServer{}).Where("id = ?", id).Update("url", url).Error
}
```

- [ ] **Step 4: Add config field on Handler**

In `internal/api/server_handlers.go`, add to the `Handler` struct:

```go
config *config.Config
```

And add an import `"github.com/hellopro/mcp-gateway/internal/config"`.

- [ ] **Step 5: Build**

Run: `go build ./...`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add internal/api/ internal/repository/server_repo.go
git commit -m "feat(mcp-gateway): add POST /template-instances upload+spawn flow"
```

### Task 10: Restart + Rotate credentials handlers

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/template_handlers.go`

- [ ] **Step 1: Add handlers**

```go
func (h *Handler) handleRestartInstance(w http.ResponseWriter, r *http.Request) {
	id := extractInstanceID(r.URL.Path, "/restart")
	if _, err := h.instanceRepo.GetByID(id); err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
		return
	}
	if err := h.runner.Restart(id); err != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner restart: " + err.Error()})
		return
	}
	_ = h.instanceRepo.UpdateStatus(id, "pending", "", nil)
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "restarting"})
}

func (h *Handler) handleRotateCredentials(w http.ResponseWriter, r *http.Request) {
	id := extractInstanceID(r.URL.Path, "/rotate-credentials")
	if err := r.ParseMultipartForm(validation.MaxSAJSONSize + 16*1024); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
	file, _, err := r.FormFile("credentials")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing credentials"})
		return
	}
	defer file.Close()
	credBytes, _ := io.ReadAll(io.LimitReader(file, int64(validation.MaxSAJSONSize)+1))
	if _, err := validation.ValidateServiceAccountJSON(credBytes); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid credentials: " + err.Error()})
		return
	}
	hash := sha256.Sum256(credBytes)
	hashHex := hex.EncodeToString(hash[:])

	inst, err := h.instanceRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
		return
	}
	tpl, _ := h.templateRepo.GetBySlug(inst.TemplateSlug)

	// Update DB first (transactional via UpdateCredentials)
	if err := h.instanceRepo.UpdateCredentials(id, credBytes, hashHex); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	// Then ask runner to respawn with new credentials
	var stdioArgs []string
	_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
	var extraEnv map[string]string
	_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
	env := renderEnv(tpl.DefaultEnv, extraEnv, id)
	if _, err := h.runner.Spawn(runnerclient.SpawnRequest{
		InstanceID: id, TemplateSlug: inst.TemplateSlug,
		StdioCommand: tpl.StdioCommand, StdioArgs: stdioArgs,
		Env: env, CredentialsJSON: string(credBytes), CredentialsHash: hashHex,
	}); err != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner respawn: " + err.Error()})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "rotating"})
}

func extractInstanceID(path, suffix string) string {
	rest := strings.TrimPrefix(path, "/api/v1/template-instances/")
	rest = strings.TrimSuffix(rest, suffix)
	return strings.TrimSuffix(rest, "/")
}
```

- [ ] **Step 2: Build**

Run: `go build ./...`

- [ ] **Step 3: Commit**

```bash
git add internal/api/template_handlers.go
git commit -m "feat(mcp-gateway): add restart + rotate-credentials handlers"
```

### Task 11: DELETE /template-instances/{id}

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/template_handlers.go`

- [ ] **Step 1: Add handler**

```go
func (h *Handler) handleDeleteInstance(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/v1/template-instances/"), "/")
	if id == "" || strings.Contains(id, "/") {
		http.NotFound(w, r)
		return
	}
	if _, err := h.instanceRepo.GetByID(id); err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
		return
	}
	// 1) Kill runner subprocess first (idempotent on runner side)
	if err := h.runner.Kill(id); err != nil {
		log.Printf("[templates] warn: runner kill failed for %s: %v", id, err)
		// do not block delete — the instance may have been orphaned
	}
	// 2) Transactional delete of template_instances + mcp_servers
	if err := h.instanceRepo.DeleteWithMCPServer(id); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
```

- [ ] **Step 2: Build + commit**

```bash
go build ./...
git add internal/api/template_handlers.go
git commit -m "feat(mcp-gateway): add DELETE /template-instances/{id}"
```

---

## Phase 7 — Gateway: Internal runner sync endpoint

### Task 12: POST /api/v1/internal/runner/sync

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/api/internal_handlers.go`

- [ ] **Step 1: Implement**

```go
package api

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/mcp-gateway/internal/runnerclient"
)

type runnerSyncResponse struct {
	DesiredInstances []runnerclient.SpawnRequest `json:"desired_instances"`
}

// handleRunnerSync is called by the runner on boot. Auth: X-Admin-Token only
// (no JWT — runner is not a user).
func (h *Handler) handleRunnerSync(w http.ResponseWriter, r *http.Request) {
	if h.config.GoogleTemplatesRunnerAdminToken == "" ||
		r.Header.Get("X-Admin-Token") != h.config.GoogleTemplatesRunnerAdminToken {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}
	instances, err := h.instanceRepo.ListAll()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	out := runnerSyncResponse{DesiredInstances: make([]runnerclient.SpawnRequest, 0, len(instances))}
	for _, inst := range instances {
		_, plain, err := h.instanceRepo.GetByIDWithCredentials(inst.ID)
		if err != nil {
			continue
		}
		tpl, err := h.templateRepo.GetBySlug(inst.TemplateSlug)
		if err != nil {
			continue
		}
		var stdioArgs []string
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
		var extraEnv map[string]string
		_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
		out.DesiredInstances = append(out.DesiredInstances, runnerclient.SpawnRequest{
			InstanceID: inst.ID, TemplateSlug: inst.TemplateSlug,
			StdioCommand: tpl.StdioCommand, StdioArgs: stdioArgs,
			Env: renderEnv(tpl.DefaultEnv, extraEnv, inst.ID),
			CredentialsJSON: string(plain), CredentialsHash: inst.CredentialsHash,
		})
	}
	writeJSON(w, http.StatusOK, out)
}
```

- [ ] **Step 2: Build + commit**

```bash
go build ./...
git add internal/api/internal_handlers.go
git commit -m "feat(mcp-gateway): add POST /api/v1/internal/runner/sync"
```

---

## Phase 8 — Gateway: Route registration + main wiring

### Task 13: Register template routes + wire main.go

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/handler.go`
- Modify: `apps-microservices/mcp-gateway-service/cmd/server/main.go`

- [ ] **Step 1: Register routes in `handler.go`**

Inside `Handler.Register(mux)`, add these blocks before the final middleware chain wrap:

```go
apiMux.HandleFunc("/api/v1/templates", func(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	h.handleListTemplates(w, r)
})
apiMux.HandleFunc("/api/v1/templates/", func(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	h.handleGetTemplate(w, r)
})

apiMux.HandleFunc("/api/v1/template-instances", func(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.handleListInstances(w, r)
	case http.MethodPost:
		h.handleCreateInstance(w, r)
	default:
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
	}
})
apiMux.HandleFunc("/api/v1/template-instances/", func(w http.ResponseWriter, r *http.Request) {
	// Route on path suffix
	switch {
	case strings.HasSuffix(r.URL.Path, "/restart"):
		if r.Method != http.MethodPost {
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleRestartInstance(w, r)
	case strings.HasSuffix(r.URL.Path, "/rotate-credentials"):
		if r.Method != http.MethodPost {
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleRotateCredentials(w, r)
	default:
		switch r.Method {
		case http.MethodGet:
			h.handleGetInstance(w, r)
		case http.MethodDelete:
			h.handleDeleteInstance(w, r)
		default:
			w.Header().Set("Allow", "GET, DELETE")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		}
	}
})

apiMux.HandleFunc("/api/v1/internal/runner/sync", func(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	h.handleRunnerSync(w, r)
})
```

- [ ] **Step 2: Update the Handler constructor / `main.go` to inject the new deps**

Find where `api.NewHandler(...)` is instantiated in `cmd/server/main.go`. Replace / extend to pass:

```go
templateRepo := repository.NewTemplateRepo(gdb)
instanceRepo := repository.NewInstanceRepo(gdb, encryptor)

var runnerClient *runnerclient.Client
if cfg.GoogleTemplatesRunnerURL != "" && cfg.GoogleTemplatesRunnerAdminToken != "" {
	runnerClient = runnerclient.New(cfg.GoogleTemplatesRunnerURL, cfg.GoogleTemplatesRunnerAdminToken)
	log.Printf("[main] google-templates runner: %s", cfg.GoogleTemplatesRunnerURL)
} else {
	log.Println("[main] google-templates runner: DISABLED (env vars not set)")
}

apiHandler := api.NewHandler(serverRepo, tokenRepo, oauth2Repo, templateRepo, instanceRepo, runnerClient, cfg /* ...existing args */)
```

Update `api.NewHandler` signature in `api/server_handlers.go` to accept the new parameters and assign them.

- [ ] **Step 3: Guard the admin-only writes behind the existing `admin` role middleware**

Find the existing admin-role guard (how `/api/v1/oauth2/clients` is guarded — grep for `admin` role in `auth/middleware.go` or `api/middleware.go`). Apply the same guard to the write endpoints:

- `POST /api/v1/template-instances`
- `POST /api/v1/template-instances/{id}/restart`
- `POST /api/v1/template-instances/{id}/rotate-credentials`
- `DELETE /api/v1/template-instances/{id}`

`GET` endpoints stay under the normal authenticated user middleware.

- [ ] **Step 4: Build**

Run: `go build ./...`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add internal/api/handler.go internal/api/server_handlers.go cmd/server/main.go
git commit -m "feat(mcp-gateway): register template + runner-sync routes and wire deps"
```

---

## Phase 9 — Runner: Service scaffold

### Task 14: Scaffold `mcp-google-templates-runner`

**Files:**
- Create: `apps-microservices/mcp-google-templates-runner/requirements.txt`
- Create: `apps-microservices/mcp-google-templates-runner/Dockerfile`
- Create: `apps-microservices/mcp-google-templates-runner/entrypoint.sh`
- Create: `apps-microservices/mcp-google-templates-runner/app/__init__.py`
- Create: `apps-microservices/mcp-google-templates-runner/app/main.py`
- Create: `apps-microservices/mcp-google-templates-runner/app/config.py`
- Create: `apps-microservices/mcp-google-templates-runner/app/auth.py`
- Create: `apps-microservices/mcp-google-templates-runner/CLAUDE.md`

- [ ] **Step 1: requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.0
pydantic-settings==2.5.0
httpx==0.27.0
mcp-proxy==0.11.0
analytics-mcp==0.5.0
mcp-gsc==0.1.5
cryptography==43.0.1
```

(Pin versions now; the engineer will bump them in a follow-up if smoke tests fail.)

- [ ] **Step 2: Dockerfile**

```dockerfile
FROM python:3.11-slim

# Tools needed for shred (coreutils ships it)
RUN apt-get update && apt-get install -y --no-install-recommends coreutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps-microservices/mcp-google-templates-runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-google-templates-runner/app /app/app
COPY apps-microservices/mcp-google-templates-runner/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Non-root
RUN useradd -u 1000 -m runner
USER runner

EXPOSE 8590
# Dynamic instance ports (from config) EXPOSEd via docker-compose expose: declarations
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8590"]
```

- [ ] **Step 3: entrypoint.sh**

```bash
#!/bin/bash
set -e
# Ensure tmpfs secret dir exists and is secure
mkdir -p /tmp/secrets
chmod 700 /tmp/secrets
exec "$@"
```

- [ ] **Step 4: app/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mcp_gateway_url: str
    mcp_gateway_admin_token: str
    runner_admin_token: str
    runner_port: int = 8590
    runner_instance_port_start: int = 15000
    runner_instance_port_end: int = 15099
    runner_host: str = "0.0.0.0"
    secrets_dir: str = "/tmp/secrets"

    class Config:
        env_prefix = ""  # env vars are already prefixed


settings = Settings()
```

- [ ] **Step 5: app/auth.py**

```python
from fastapi import Header, HTTPException, status
from app.config import settings


async def require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not x_admin_token or x_admin_token != settings.runner_admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
```

- [ ] **Step 6: app/main.py (skeleton)**

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger("runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("runner starting; gateway=%s port_pool=%d-%d",
                settings.mcp_gateway_url,
                settings.runner_instance_port_start,
                settings.runner_instance_port_end)
    # Filled in by Task 18 (supervisor wiring) + Task 19 (startup sync)
    yield
    logger.info("runner shutting down")
    # Filled in by Task 18: await supervisor.shutdown()


app = FastAPI(title="mcp-google-templates-runner", lifespan=lifespan)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: CLAUDE.md**

```markdown
# mcp-google-templates-runner

Python sidecar that hosts stdio MCP servers spawned by the gateway's Templates feature. One `mcp-proxy` subprocess per uploaded service-account JSON, each on a dynamic port in the 15000–15099 pool, supervised per-instance.

## Tech Stack

- Python 3.11, FastAPI, Uvicorn, asyncio
- `mcp-proxy` wraps stdio MCP servers into SSE/HTTP
- Upstream packages: `analytics-mcp` (GA4), `mcp-gsc` (Search Console)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_URL` | — | Base URL of mcp-gateway-service for startup sync |
| `MCP_GATEWAY_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` to the gateway |
| `RUNNER_ADMIN_TOKEN` | — | Required `X-Admin-Token` on incoming `/admin/*` requests |
| `RUNNER_PORT` | `8590` | Admin API port |
| `RUNNER_INSTANCE_PORT_START` | `15000` | First port in the dynamic pool |
| `RUNNER_INSTANCE_PORT_END` | `15099` | Last port in the dynamic pool |
| `SECRETS_DIR` | `/tmp/secrets` | Tmpfs dir for per-instance credential files |

## Admin API (X-Admin-Token)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/health` | Liveness |
| `GET` | `/admin/instances` | List running instances |
| `POST` | `/admin/instances` | Spawn instance |
| `DELETE` | `/admin/instances/{id}` | Kill + shred credentials |
| `POST` | `/admin/instances/{id}/restart` | Restart in place |
| `POST` | `/admin/reconcile` | Full state reconcile (used on startup) |

See `docs/superpowers/specs/2026-04-17-google-templates-dynamic-secrets-design.md` for the full design.
```

- [ ] **Step 8: Build the image**

```bash
cd /home/sandratra/RAG-HP-PUB
docker build -f apps-microservices/mcp-google-templates-runner/Dockerfile -t mcp-google-templates-runner:local .
```

Expected: build succeeds

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/mcp-google-templates-runner/
git commit -m "feat(templates-runner): scaffold FastAPI service + health endpoint"
```

---

## Phase 10 — Runner: Port pool

### Task 15: Port allocator

**Files:**
- Create: `apps-microservices/mcp-google-templates-runner/app/port_pool.py`
- Create: `apps-microservices/mcp-google-templates-runner/tests/__init__.py`
- Create: `apps-microservices/mcp-google-templates-runner/tests/test_port_pool.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_port_pool.py
import pytest
from app.port_pool import PortPool, PortPoolExhausted


def test_allocate_in_order():
    pool = PortPool(15000, 15002)
    assert pool.allocate() == 15000
    assert pool.allocate() == 15001
    assert pool.allocate() == 15002


def test_release_makes_available():
    pool = PortPool(15000, 15000)
    p = pool.allocate()
    pool.release(p)
    assert pool.allocate() == p


def test_exhausted_raises():
    pool = PortPool(15000, 15000)
    pool.allocate()
    with pytest.raises(PortPoolExhausted):
        pool.allocate()


def test_release_unknown_is_noop():
    pool = PortPool(15000, 15001)
    pool.release(9999)
    assert pool.allocate() == 15000
```

- [ ] **Step 2: Run, verify fails**

```bash
cd apps-microservices/mcp-google-templates-runner
pip install -r requirements.txt pytest pytest-asyncio
pytest tests/test_port_pool.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Implement**

```python
# app/port_pool.py
from __future__ import annotations
import threading


class PortPoolExhausted(Exception):
    pass


class PortPool:
    def __init__(self, start: int, end: int):
        if end < start:
            raise ValueError("end must be >= start")
        self._start = start
        self._end = end
        self._used: set[int] = set()
        self._lock = threading.Lock()

    def allocate(self) -> int:
        with self._lock:
            for p in range(self._start, self._end + 1):
                if p not in self._used:
                    self._used.add(p)
                    return p
            raise PortPoolExhausted(f"no free port in [{self._start}, {self._end}]")

    def release(self, port: int) -> None:
        with self._lock:
            self._used.discard(port)

    def used(self) -> list[int]:
        with self._lock:
            return sorted(self._used)
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_port_pool.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-google-templates-runner/app/port_pool.py apps-microservices/mcp-google-templates-runner/tests/
git commit -m "feat(templates-runner): add thread-safe port allocator"
```

---

## Phase 11 — Runner: Credentials manager

### Task 16: Credentials tmpfs writer + shredder

**Files:**
- Create: `apps-microservices/mcp-google-templates-runner/app/credentials.py`
- Create: `apps-microservices/mcp-google-templates-runner/tests/test_credentials.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_credentials.py
import os
import pytest
from pathlib import Path

from app.credentials import CredentialsStore


@pytest.fixture
def tmp_store(tmp_path):
    return CredentialsStore(base_dir=str(tmp_path))


def test_write_creates_file_mode_600(tmp_store):
    p = tmp_store.write("abc", "{\"x\":1}")
    assert Path(p).is_file()
    assert oct(Path(p).stat().st_mode)[-3:] == "600"


def test_shred_removes_file(tmp_store):
    p = tmp_store.write("abc", "{}")
    tmp_store.shred("abc")
    assert not Path(p).exists()


def test_shred_missing_is_noop(tmp_store):
    tmp_store.shred("never-existed")


def test_path_is_predictable(tmp_store):
    p1 = tmp_store.write("abc", "{}")
    p2 = tmp_store.path_for("abc")
    assert p1 == p2
```

- [ ] **Step 2: Run, verify fails**

```bash
pytest tests/test_credentials.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# app/credentials.py
from __future__ import annotations
import os
import subprocess
from pathlib import Path


class CredentialsStore:
    def __init__(self, base_dir: str):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        os.chmod(self._base, 0o700)

    def path_for(self, instance_id: str) -> str:
        return str(self._base / f"{instance_id}.json")

    def write(self, instance_id: str, plaintext: str) -> str:
        p = self.path_for(instance_id)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, plaintext.encode("utf-8"))
        finally:
            os.close(fd)
        return p

    def shred(self, instance_id: str) -> None:
        p = self.path_for(instance_id)
        if not os.path.exists(p):
            return
        # Best-effort shred. On tmpfs this is roughly equivalent to unlink
        # (no persistent media), but keep the call for defence in depth.
        try:
            subprocess.run(["shred", "-u", p], check=False, timeout=5)
        except Exception:
            pass
        if os.path.exists(p):
            os.remove(p)
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_credentials.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-google-templates-runner/app/credentials.py apps-microservices/mcp-google-templates-runner/tests/test_credentials.py
git commit -m "feat(templates-runner): add credentials store with tmpfs shred"
```

---

## Phase 12 — Runner: Supervisor

### Task 17: Per-instance asyncio supervisor

**Files:**
- Create: `apps-microservices/mcp-google-templates-runner/app/supervisor.py`
- Create: `apps-microservices/mcp-google-templates-runner/tests/test_supervisor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_supervisor.py
import asyncio
import time
from pathlib import Path

import pytest

from app.port_pool import PortPool
from app.credentials import CredentialsStore
from app.supervisor import Supervisor, SpawnSpec


@pytest.fixture
async def supervisor(tmp_path):
    pool = PortPool(20000, 20099)
    store = CredentialsStore(base_dir=str(tmp_path))
    sup = Supervisor(pool=pool, credentials=store)
    yield sup
    await sup.shutdown()


@pytest.mark.asyncio
async def test_spawn_and_kill_simple_subprocess(supervisor):
    # Use `sleep` as a stand-in for mcp-proxy
    spec = SpawnSpec(
        instance_id="it1",
        template_slug="test",
        stdio_command="sleep",
        stdio_args=["3600"],
        env={},
        credentials_json='{"type":"service_account"}',
        credentials_hash="deadbeef",
    )
    inst = await supervisor.spawn(spec, bypass_mcp_proxy=True)
    assert inst.port in range(20000, 20100)
    assert inst.pid > 0
    await supervisor.kill("it1")
    assert supervisor.get("it1") is None


@pytest.mark.asyncio
async def test_crashing_child_is_respawned(supervisor):
    spec = SpawnSpec(
        instance_id="it2",
        template_slug="test",
        stdio_command="sh",
        stdio_args=["-c", "sleep 0.5; exit 1"],
        env={},
        credentials_json="{}",
        credentials_hash="h",
    )
    inst = await supervisor.spawn(spec, bypass_mcp_proxy=True)
    first_pid = inst.pid
    await asyncio.sleep(2.0)
    assert supervisor.get("it2").pid != first_pid


@pytest.mark.asyncio
async def test_flapping_marks_failed(supervisor):
    spec = SpawnSpec(
        instance_id="it3",
        template_slug="test",
        stdio_command="sh",
        stdio_args=["-c", "exit 1"],
        env={},
        credentials_json="{}",
        credentials_hash="h",
    )
    await supervisor.spawn(spec, bypass_mcp_proxy=True)
    # Wait long enough for 5 fast exits
    await asyncio.sleep(3.0)
    inst = supervisor.get("it3")
    assert inst is None or inst.status == "failed"
```

- [ ] **Step 2: Run, verify fails**

```bash
pytest tests/test_supervisor.py -v
```

Expected: FAIL (module missing)

- [ ] **Step 3: Implement `app/supervisor.py`**

```python
# app/supervisor.py
from __future__ import annotations

import asyncio
import collections
import dataclasses
import logging
import signal
import time
from typing import Optional

from app.port_pool import PortPool
from app.credentials import CredentialsStore

logger = logging.getLogger("supervisor")


@dataclasses.dataclass
class SpawnSpec:
    instance_id: str
    template_slug: str
    stdio_command: str
    stdio_args: list[str]
    env: dict[str, str]
    credentials_json: str
    credentials_hash: str


@dataclasses.dataclass
class RunningInstance:
    instance_id: str
    template_slug: str
    port: int
    pid: int
    credentials_path: str
    credentials_hash: str
    spec: SpawnSpec
    desired_state: str  # "running" | "stopped"
    status: str         # "pending" | "running" | "failed" | "stopped"
    last_error: str
    stderr_ring: collections.deque
    exit_count: int
    started_at: float
    supervisor_task: Optional[asyncio.Task] = None
    process: Optional[asyncio.subprocess.Process] = None


class Supervisor:
    FLAPPING_THRESHOLD = 5
    FLAPPING_WINDOW_SEC = 10.0
    BACKOFF_INITIAL = 1.0
    BACKOFF_MAX = 60.0
    HEALTHY_RESET_SEC = 60.0
    STDERR_RING_SIZE = 200

    def __init__(self, pool: PortPool, credentials: CredentialsStore):
        self._pool = pool
        self._creds = credentials
        self._instances: dict[str, RunningInstance] = {}
        self._lock = asyncio.Lock()

    def get(self, instance_id: str) -> Optional[RunningInstance]:
        return self._instances.get(instance_id)

    def list(self) -> list[RunningInstance]:
        return list(self._instances.values())

    async def spawn(self, spec: SpawnSpec, bypass_mcp_proxy: bool = False) -> RunningInstance:
        async with self._lock:
            if spec.instance_id in self._instances:
                # Spawn-on-existing = restart-with-possibly-new-spec
                await self._kill_locked(spec.instance_id, release_port=False)
            port = self._pool.allocate()
            cred_path = self._creds.write(spec.instance_id, spec.credentials_json)
            inst = RunningInstance(
                instance_id=spec.instance_id,
                template_slug=spec.template_slug,
                port=port, pid=0,
                credentials_path=cred_path,
                credentials_hash=spec.credentials_hash,
                spec=spec,
                desired_state="running",
                status="pending",
                last_error="",
                stderr_ring=collections.deque(maxlen=self.STDERR_RING_SIZE),
                exit_count=0,
                started_at=time.monotonic(),
            )
            self._instances[spec.instance_id] = inst
            inst.supervisor_task = asyncio.create_task(
                self._supervise(inst, bypass_mcp_proxy=bypass_mcp_proxy)
            )
        # Give the supervisor a moment to launch
        await asyncio.sleep(0.1)
        return inst

    async def kill(self, instance_id: str) -> None:
        async with self._lock:
            await self._kill_locked(instance_id, release_port=True)

    async def _kill_locked(self, instance_id: str, release_port: bool) -> None:
        inst = self._instances.pop(instance_id, None)
        if not inst:
            return
        inst.desired_state = "stopped"
        if inst.process and inst.process.returncode is None:
            try:
                inst.process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(inst.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    inst.process.kill()
                    await inst.process.wait()
            except ProcessLookupError:
                pass
        if inst.supervisor_task and not inst.supervisor_task.done():
            inst.supervisor_task.cancel()
        if release_port:
            self._pool.release(inst.port)
        self._creds.shred(inst.instance_id)

    async def restart(self, instance_id: str) -> None:
        inst = self._instances.get(instance_id)
        if not inst:
            raise KeyError(instance_id)
        # Respawn with the same spec (supervisor's loop will restart after kill)
        if inst.process and inst.process.returncode is None:
            inst.process.send_signal(signal.SIGTERM)

    async def shutdown(self) -> None:
        async with self._lock:
            for iid in list(self._instances.keys()):
                await self._kill_locked(iid, release_port=True)

    async def _supervise(self, inst: RunningInstance, bypass_mcp_proxy: bool) -> None:
        backoff = self.BACKOFF_INITIAL
        while inst.desired_state == "running":
            # Build argv
            if bypass_mcp_proxy:
                argv = [inst.spec.stdio_command, *inst.spec.stdio_args]
            else:
                argv = [
                    "mcp-proxy",
                    "--port", str(inst.port),
                    "--host", "0.0.0.0",
                    "--pass-environment",
                    "--stateless",
                    "--", inst.spec.stdio_command, *inst.spec.stdio_args,
                ]
            proc_env = {**inst.spec.env}
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    env=proc_env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                )
            except FileNotFoundError as e:
                inst.last_error = f"spawn failed: {e}"
                inst.status = "failed"
                logger.error("instance %s: %s", inst.instance_id, inst.last_error)
                return

            inst.process = proc
            inst.pid = proc.pid
            inst.status = "running"
            inst.started_at = time.monotonic()
            logger.info("instance %s: started pid=%d port=%d", inst.instance_id, proc.pid, inst.port)

            drain_task = asyncio.create_task(self._drain_stderr(inst))
            try:
                exit_code = await proc.wait()
            finally:
                drain_task.cancel()

            if inst.desired_state != "running":
                inst.status = "stopped"
                return

            inst.exit_count += 1
            tail = "\n".join(list(inst.stderr_ring)[-10:])
            inst.last_error = f"exit {exit_code}; stderr tail:\n{tail}"
            logger.warning("instance %s exited: %s", inst.instance_id, inst.last_error)

            # Flapping detection
            uptime = time.monotonic() - inst.started_at
            if uptime < self.FLAPPING_WINDOW_SEC and inst.exit_count >= self.FLAPPING_THRESHOLD:
                inst.status = "failed"
                inst.desired_state = "stopped"
                return

            # Healthy long-run resets backoff and exit counter
            if uptime > self.HEALTHY_RESET_SEC:
                backoff = self.BACKOFF_INITIAL
                inst.exit_count = 0

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.BACKOFF_MAX)

        inst.status = "stopped"

    async def _drain_stderr(self, inst: RunningInstance) -> None:
        assert inst.process and inst.process.stderr
        try:
            while True:
                line = await inst.process.stderr.readline()
                if not line:
                    return
                inst.stderr_ring.append(line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            return
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/test_supervisor.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-google-templates-runner/app/supervisor.py apps-microservices/mcp-google-templates-runner/tests/test_supervisor.py
git commit -m "feat(templates-runner): add per-instance supervisor with backoff + flapping detection"
```

---

## Phase 13 — Runner: Admin API

### Task 18: /admin/instances endpoints

**Files:**
- Create: `apps-microservices/mcp-google-templates-runner/app/models.py`
- Create: `apps-microservices/mcp-google-templates-runner/app/api/__init__.py`
- Create: `apps-microservices/mcp-google-templates-runner/app/api/admin.py`
- Modify: `apps-microservices/mcp-google-templates-runner/app/main.py`

- [ ] **Step 1: Define pydantic models in `app/models.py`**

```python
from pydantic import BaseModel


class SpawnRequest(BaseModel):
    instance_id: str
    template_slug: str
    stdio_command: str
    stdio_args: list[str] = []
    env: dict[str, str] = {}
    credentials_json: str
    credentials_hash: str


class SpawnResponse(BaseModel):
    port: int
    pid: int


class InstanceStatus(BaseModel):
    id: str
    port: int
    pid: int
    status: str
    uptime_s: int
    last_error: str | None = None
    stderr_tail: str | None = None


class InstanceListResponse(BaseModel):
    instances: list[InstanceStatus]


class ReconcileRequest(BaseModel):
    desired_instances: list[SpawnRequest]
```

- [ ] **Step 2: Implement `app/api/admin.py`**

```python
from __future__ import annotations
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin_token
from app.models import (
    SpawnRequest, SpawnResponse, InstanceStatus, InstanceListResponse, ReconcileRequest,
)
from app.supervisor import Supervisor, SpawnSpec

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_token)])


def get_supervisor() -> Supervisor:
    # set by main.py at startup
    from app import main
    if main.supervisor is None:
        raise HTTPException(503, "supervisor not ready")
    return main.supervisor


@router.get("/instances", response_model=InstanceListResponse)
async def list_instances(sup: Supervisor = Depends(get_supervisor)):
    items = []
    for inst in sup.list():
        items.append(InstanceStatus(
            id=inst.instance_id, port=inst.port, pid=inst.pid,
            status=inst.status,
            uptime_s=int(time.monotonic() - inst.started_at) if inst.status == "running" else 0,
            last_error=inst.last_error or None,
            stderr_tail="\n".join(list(inst.stderr_ring)) or None,
        ))
    return InstanceListResponse(instances=items)


@router.post("/instances", response_model=SpawnResponse)
async def spawn_instance(req: SpawnRequest, sup: Supervisor = Depends(get_supervisor)):
    spec = SpawnSpec(**req.model_dump())
    try:
        inst = await sup.spawn(spec)
    except Exception as e:
        raise HTTPException(500, f"spawn failed: {e}")
    return SpawnResponse(port=inst.port, pid=inst.pid)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kill_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    await sup.kill(instance_id)
    return None


@router.post("/instances/{instance_id}/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    try:
        await sup.restart(instance_id)
    except KeyError:
        raise HTTPException(404, "instance not found")
    return {"status": "restarting"}


@router.post("/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile(req: ReconcileRequest, sup: Supervisor = Depends(get_supervisor)):
    desired = {r.instance_id: r for r in req.desired_instances}
    local = {inst.instance_id: inst for inst in sup.list()}

    # Kill extras
    for iid in list(local.keys()):
        if iid not in desired:
            await sup.kill(iid)

    # Spawn missing + restart hash mismatches (bounded concurrency = 5)
    sem = asyncio.Semaphore(5)

    async def _spawn_one(r: SpawnRequest):
        async with sem:
            await sup.spawn(SpawnSpec(**r.model_dump()))

    to_spawn = []
    for iid, r in desired.items():
        if iid not in local:
            to_spawn.append(r)
        elif local[iid].credentials_hash != r.credentials_hash:
            to_spawn.append(r)

    await asyncio.gather(*[_spawn_one(r) for r in to_spawn])
    return {"spawned": len(to_spawn)}
```

- [ ] **Step 3: Wire the router into `main.py`**

Replace the earlier skeleton with:

```python
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.port_pool import PortPool
from app.credentials import CredentialsStore
from app.supervisor import Supervisor
from app.api.admin import router as admin_router

logger = logging.getLogger("runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

supervisor: Supervisor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global supervisor
    pool = PortPool(settings.runner_instance_port_start, settings.runner_instance_port_end)
    creds = CredentialsStore(settings.secrets_dir)
    supervisor = Supervisor(pool=pool, credentials=creds)
    logger.info("runner started; gateway=%s ports=%d-%d",
                settings.mcp_gateway_url,
                settings.runner_instance_port_start,
                settings.runner_instance_port_end)
    # Startup sync — added in Task 19
    yield
    if supervisor:
        await supervisor.shutdown()
    logger.info("runner shut down")


app = FastAPI(title="mcp-google-templates-runner", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
```

Note: `/admin/health` is intentionally at the app root (not the router) so it doesn't require the admin token — used for Docker healthcheck.

- [ ] **Step 4: Write test for admin API**

```python
# tests/test_admin_api.py
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://localhost:0")
    monkeypatch.setenv("MCP_GATEWAY_ADMIN_TOKEN", "t")
    monkeypatch.setenv("RUNNER_ADMIN_TOKEN", "t")
    with TestClient(app) as c:
        yield c


def test_health_no_auth(client):
    r = client.get("/admin/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_requires_token(client):
    r = client.get("/admin/instances")
    assert r.status_code == 401


def test_list_with_token(client):
    r = client.get("/admin/instances", headers={"X-Admin-Token": "t"})
    assert r.status_code == 200
    assert r.json() == {"instances": []}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-google-templates-runner/app/ apps-microservices/mcp-google-templates-runner/tests/
git commit -m "feat(templates-runner): add /admin/* endpoints (list, spawn, kill, restart, reconcile)"
```

---

## Phase 14 — Runner: Startup sync with gateway

### Task 19: Gateway sync on boot

**Files:**
- Create: `apps-microservices/mcp-google-templates-runner/app/gateway_sync.py`
- Modify: `apps-microservices/mcp-google-templates-runner/app/main.py`

- [ ] **Step 1: Implement `gateway_sync.py`**

```python
# app/gateway_sync.py
from __future__ import annotations
import asyncio
import logging

import httpx

from app.config import settings
from app.supervisor import Supervisor, SpawnSpec

logger = logging.getLogger("runner.sync")


async def sync_with_gateway(sup: Supervisor, retries: int = 5) -> None:
    """On boot, fetch desired instances from the gateway and spawn them."""
    url = settings.mcp_gateway_url.rstrip("/") + "/api/v1/internal/runner/sync"
    headers = {"X-Admin-Token": settings.mcp_gateway_admin_token}
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json={})
                resp.raise_for_status()
                body = resp.json()
            desired = body.get("desired_instances", [])
            logger.info("startup sync: %d desired instances", len(desired))
            sem = asyncio.Semaphore(5)

            async def _spawn(spec_dict):
                async with sem:
                    await sup.spawn(SpawnSpec(**spec_dict))

            await asyncio.gather(*[_spawn(d) for d in desired], return_exceptions=True)
            return
        except Exception as e:
            logger.warning("startup sync attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(min(2 ** attempt, 30))
    logger.error("startup sync: giving up after %d attempts — running with empty state", retries)
```

- [ ] **Step 2: Wire into `main.py` lifespan**

Replace the `# Startup sync — added in Task 19` placeholder with:

```python
from app.gateway_sync import sync_with_gateway
# ... inside lifespan ...
asyncio.create_task(sync_with_gateway(supervisor))
```

- [ ] **Step 3: Build**

```bash
docker build -f apps-microservices/mcp-google-templates-runner/Dockerfile -t mcp-google-templates-runner:local .
```

Expected: success

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-google-templates-runner/app/
git commit -m "feat(templates-runner): fetch desired state from gateway on boot"
```

---

## Phase 15 — Docker compose

### Task 20: Add runner to docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example` (or equivalent)

- [ ] **Step 1: Locate the `mcp-gateway-service` block in `docker-compose.yml` and add this service next to it**

```yaml
  mcp-google-templates-runner:
    profiles: ["mcp"]
    build:
      context: .
      dockerfile: apps-microservices/mcp-google-templates-runner/Dockerfile
    image: mcp-google-templates-runner:local
    restart: unless-stopped
    environment:
      MCP_GATEWAY_URL: "http://mcp-gateway-service:8560"
      MCP_GATEWAY_ADMIN_TOKEN: "${GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN}"
      RUNNER_ADMIN_TOKEN: "${GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN}"
      RUNNER_PORT: "8590"
      RUNNER_INSTANCE_PORT_START: "15000"
      RUNNER_INSTANCE_PORT_END: "15099"
    expose:
      - "8590"
      - "15000-15099"
    tmpfs:
      - /tmp/secrets:mode=700,uid=1000,size=16m
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8590/admin/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    depends_on:
      - mcp-gateway-service
    networks:
      - default
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**Verify before committing**: `curl` must be installed in the runner image for the healthcheck. Add `curl` to the `apt-get install` in the Dockerfile if it isn't there already:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends coreutils curl \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Extend `mcp-gateway-service` env vars in the same compose file**

```yaml
      GOOGLE_TEMPLATES_RUNNER_URL: "http://mcp-google-templates-runner:8590"
      GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN: "${GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN}"
```

- [ ] **Step 3: Update `.env.example`**

Append:

```
# mcp-google-templates-runner
GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN=change-me-to-a-random-secret
```

- [ ] **Step 4: Smoke test**

```bash
docker compose --profile mcp up -d mcp-google-templates-runner
docker compose logs mcp-google-templates-runner --tail 50
curl -s http://localhost:8590/admin/health
```

Expected: `{"status":"ok"}` (access it directly only if port is exposed locally; otherwise `docker compose exec`).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example apps-microservices/mcp-google-templates-runner/Dockerfile
git commit -m "feat(compose): add mcp-google-templates-runner service"
```

---

## Phase 16 — Seed templates

### Task 21: Insert GA + GSC seed rows

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/init-db/init-mcp-gateway-db.sql`

- [ ] **Step 1: Append to the SQL file**

```sql
-- Templates catalog seed
INSERT INTO templates (slug, name, description, icon, stdio_command, stdio_args, default_env, required_extra_env, tool_prefix, tags, is_active, created_at, updated_at)
VALUES
  ('ga',
   'Google Analytics 4',
   'MCP wrapper exposing GA4 accounts, properties, and reports (read-only).',
   '',
   'analytics-mcp',
   '[]',
   '{"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/secrets/{instance_id}.json"}',
   '[{"key":"GOOGLE_PROJECT_ID","label":"GCP project ID","required":true}]',
   'ga',
   '["analytics","google"]',
   1,
   NOW(3), NOW(3)),
  ('gsc',
   'Google Search Console',
   'MCP wrapper for Search Console search analytics and URL inspection.',
   '',
   'mcp-gsc',
   '[]',
   '{"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/secrets/{instance_id}.json", "GSC_SKIP_OAUTH": "true"}',
   '[{"key":"GSC_SITE_URL","label":"Search Console property URL","required":true}]',
   'gsc',
   '["seo","google","search-console"]',
   1,
   NOW(3), NOW(3))
ON DUPLICATE KEY UPDATE
  name=VALUES(name),
  description=VALUES(description),
  stdio_command=VALUES(stdio_command),
  default_env=VALUES(default_env),
  required_extra_env=VALUES(required_extra_env),
  tool_prefix=VALUES(tool_prefix),
  tags=VALUES(tags),
  updated_at=NOW(3);
```

- [ ] **Step 2: Apply + verify**

```bash
docker compose exec mysql mysql -u root -p<DB_PASSWORD> mcp_gateway < apps-microservices/mcp-gateway-service/init-db/init-mcp-gateway-db.sql
docker compose exec mysql mysql -u root -p<DB_PASSWORD> mcp_gateway -e "SELECT slug, name, is_active FROM templates;"
```

Expected: two rows (`ga`, `gsc`).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/init-db/init-mcp-gateway-db.sql
git commit -m "feat(mcp-gateway): seed templates catalog with GA + GSC"
```

---

## Phase 17 — Frontend

### Task 22: API client + types + Pinia store

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/types/templates.ts`
- Create: `apps-microservices/mcp-gateway-frontend/src/api/templates.ts`
- Create: `apps-microservices/mcp-gateway-frontend/src/stores/templates.ts`

- [ ] **Step 1: Types**

```ts
// src/types/templates.ts
export interface Template {
  slug: string;
  name: string;
  description: string;
  icon: string;
  stdio_command: string;
  required_extra_env: { key: string; label: string; required: boolean }[];
  tool_prefix: string;
  tags: string[];
  instance_count: number;
}

export type InstanceStatus = 'pending' | 'running' | 'failed' | 'stopped';

export interface TemplateInstance {
  id: string;
  template_slug: string;
  name: string;
  extra_env?: Record<string, string>;
  runner_port?: number;
  runner_status: InstanceStatus;
  runner_last_error?: string;
  mcp_server_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  stderr_tail?: string;
}
```

- [ ] **Step 2: API client (match existing client style — `src/api/servers.ts` as reference)**

```ts
// src/api/templates.ts
import { apiClient } from './client'; // existing wrapper
import type { Template, TemplateInstance } from '@/types/templates';

export const templatesApi = {
  async list(): Promise<Template[]> {
    const { data } = await apiClient.get('/api/v1/templates');
    return data.templates;
  },
  async get(slug: string): Promise<Template> {
    const { data } = await apiClient.get(`/api/v1/templates/${slug}`);
    return data;
  },
  async listInstances(slug?: string): Promise<TemplateInstance[]> {
    const { data } = await apiClient.get('/api/v1/template-instances', {
      params: slug ? { template_slug: slug } : undefined,
    });
    return data.instances;
  },
  async getInstance(id: string): Promise<TemplateInstance> {
    const { data } = await apiClient.get(`/api/v1/template-instances/${id}`);
    return data;
  },
  async createInstance(params: {
    template_slug: string;
    name: string;
    extra_env?: Record<string, string>;
    credentials: File;
  }): Promise<TemplateInstance> {
    const fd = new FormData();
    fd.append('template_slug', params.template_slug);
    fd.append('name', params.name);
    if (params.extra_env) fd.append('extra_env', JSON.stringify(params.extra_env));
    fd.append('credentials', params.credentials);
    const { data } = await apiClient.post('/api/v1/template-instances', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
  async restart(id: string): Promise<void> {
    await apiClient.post(`/api/v1/template-instances/${id}/restart`);
  },
  async rotate(id: string, credentials: File): Promise<void> {
    const fd = new FormData();
    fd.append('credentials', credentials);
    await apiClient.post(`/api/v1/template-instances/${id}/rotate-credentials`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  async delete(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/template-instances/${id}`);
  },
};
```

- [ ] **Step 3: Pinia store**

```ts
// src/stores/templates.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { templatesApi } from '@/api/templates';
import type { Template, TemplateInstance } from '@/types/templates';

export const useTemplatesStore = defineStore('templates', () => {
  const templates = ref<Template[]>([]);
  const instances = ref<TemplateInstance[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function loadTemplates() {
    loading.value = true;
    error.value = null;
    try {
      templates.value = await templatesApi.list();
    } catch (e: any) {
      error.value = e?.response?.data?.error ?? e.message;
    } finally {
      loading.value = false;
    }
  }

  async function loadInstances(slug?: string) {
    loading.value = true;
    try {
      instances.value = await templatesApi.listInstances(slug);
    } finally {
      loading.value = false;
    }
  }

  async function createInstance(p: Parameters<typeof templatesApi.createInstance>[0]) {
    const inst = await templatesApi.createInstance(p);
    instances.value.unshift(inst);
    return inst;
  }

  async function deleteInstance(id: string) {
    await templatesApi.delete(id);
    instances.value = instances.value.filter(i => i.id !== id);
  }

  async function restartInstance(id: string) {
    await templatesApi.restart(id);
  }

  async function rotateCredentials(id: string, file: File) {
    await templatesApi.rotate(id, file);
  }

  return { templates, instances, loading, error,
    loadTemplates, loadInstances, createInstance, deleteInstance, restartInstance, rotateCredentials };
});
```

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/types/templates.ts apps-microservices/mcp-gateway-frontend/src/api/templates.ts apps-microservices/mcp-gateway-frontend/src/stores/templates.ts
git commit -m "feat(mcp-gateway-frontend): add templates API client, types, store"
```

### Task 23: Router + NavBar entry

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/router/index.ts`
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/NavBar.vue` (or equivalent main nav file — grep for the existing `Servers` tab markup)

- [ ] **Step 1: Add routes**

```ts
// src/router/index.ts — inside the routes array
{
  path: '/admin/templates',
  name: 'templates',
  component: () => import('@/views/TemplatesView.vue'),
  meta: { requiresAuth: true, requiresAdmin: true },
},
{
  path: '/admin/templates/:slug',
  name: 'template-detail',
  component: () => import('@/views/TemplateDetailView.vue'),
  meta: { requiresAuth: true, requiresAdmin: true },
  props: true,
},
```

- [ ] **Step 2: Add NavBar link** (copy the pattern of the `Servers` or `Tokens` entry)

```vue
<router-link to="/admin/templates" class="nav-item" v-if="isAdmin">
  Templates
</router-link>
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/router/ apps-microservices/mcp-gateway-frontend/src/components/NavBar.vue
git commit -m "feat(mcp-gateway-frontend): add Templates route + NavBar link"
```

### Task 24: TemplatesView (catalog)

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/views/TemplatesView.vue`

- [ ] **Step 1: Implement (match styling conventions — grep an existing list view like `ServersView.vue` for card styles)**

```vue
<template>
  <div class="templates-view">
    <header>
      <h1>Templates</h1>
      <p class="subtitle">Pre-configured MCP wrappers. Add an instance by uploading credentials.</p>
    </header>

    <div v-if="store.loading && !store.templates.length" class="loading">Loading…</div>
    <div v-if="store.error" class="error">{{ store.error }}</div>

    <ul class="template-list">
      <li v-for="t in store.templates" :key="t.slug" class="template-card">
        <router-link :to="`/admin/templates/${t.slug}`">
          <div class="icon">{{ t.icon || '🧩' }}</div>
          <div class="grow">
            <h3>{{ t.name }}</h3>
            <p>{{ t.stdio_command }} · {{ t.instance_count }} instance(s)</p>
          </div>
          <span class="chevron">→</span>
        </router-link>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useTemplatesStore } from '@/stores/templates';

const store = useTemplatesStore();
onMounted(() => store.loadTemplates());
</script>

<style scoped>
.template-list { list-style: none; padding: 0; }
.template-card a { display: flex; align-items: center; gap: 12px; padding: 12px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; text-decoration: none; color: inherit; }
.template-card a:hover { background: var(--hover); }
.icon { font-size: 1.5rem; }
.grow { flex: 1; }
.error { color: var(--error); }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/views/TemplatesView.vue
git commit -m "feat(mcp-gateway-frontend): add TemplatesView catalog"
```

### Task 25: TemplateDetailView + InstanceCard

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/views/TemplateDetailView.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/templates/TemplateInstanceCard.vue`

- [ ] **Step 1: `TemplateInstanceCard.vue`**

```vue
<template>
  <div class="instance-card" :class="inst.runner_status">
    <div class="grow">
      <h4>
        {{ inst.name }}
        <span class="pill" :class="inst.runner_status">{{ inst.runner_status }}</span>
      </h4>
      <p class="meta">
        <span v-if="inst.runner_port">port {{ inst.runner_port }}</span>
        <span v-if="inst.runner_last_error" class="error"> · {{ inst.runner_last_error }}</span>
      </p>
    </div>
    <div class="actions">
      <button @click="$emit('rotate', inst)">Rotate JSON</button>
      <button @click="$emit('restart', inst)">Restart</button>
      <button class="danger" @click="$emit('delete', inst)">Delete</button>
      <button v-if="inst.runner_status === 'failed'" @click="$emit('logs', inst)">View logs</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TemplateInstance } from '@/types/templates';
defineProps<{ inst: TemplateInstance }>();
defineEmits<{
  (e: 'rotate' | 'restart' | 'delete' | 'logs', inst: TemplateInstance): void;
}>();
</script>

<style scoped>
.instance-card { display: flex; align-items: center; gap: 12px; padding: 12px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; }
.pill { font-size: 0.75em; padding: 2px 6px; border-radius: 3px; }
.pill.running { background: var(--success-bg); color: var(--success-fg); }
.pill.failed { background: var(--error-bg); color: var(--error-fg); }
.pill.pending { background: var(--warn-bg); color: var(--warn-fg); }
.actions button { margin-left: 4px; }
.danger { color: var(--error-fg); }
</style>
```

- [ ] **Step 2: `TemplateDetailView.vue`**

```vue
<template>
  <div class="template-detail">
    <router-link to="/admin/templates" class="back">← Templates</router-link>
    <header v-if="template">
      <h1>{{ template.name }}</h1>
      <p class="subtitle">Wraps <code>{{ template.stdio_command }}</code></p>
      <button @click="showAdd = true" class="primary">+ Add instance</button>
    </header>

    <section>
      <h2>Instances ({{ instances.length }})</h2>
      <TemplateInstanceCard
        v-for="inst in instances"
        :key="inst.id"
        :inst="inst"
        @rotate="onRotate"
        @restart="onRestart"
        @delete="onDelete"
        @logs="onLogs"
      />
      <p v-if="!instances.length" class="empty">No instances yet — click "Add instance" to upload a service-account JSON.</p>
    </section>

    <AddInstanceModal
      v-if="showAdd && template"
      :template="template"
      @close="showAdd = false"
      @created="onCreated"
    />

    <RotateCredentialsModal
      v-if="rotateTarget"
      :instance="rotateTarget"
      @close="rotateTarget = null"
      @rotated="onRotated"
    />

    <InstanceLogsModal
      v-if="logsTarget"
      :instance="logsTarget"
      @close="logsTarget = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watchEffect } from 'vue';
import { useRoute } from 'vue-router';
import { useTemplatesStore } from '@/stores/templates';
import { templatesApi } from '@/api/templates';
import TemplateInstanceCard from '@/components/templates/TemplateInstanceCard.vue';
import AddInstanceModal from '@/components/templates/AddInstanceModal.vue';
import RotateCredentialsModal from '@/components/templates/RotateCredentialsModal.vue';
import InstanceLogsModal from '@/components/templates/InstanceLogsModal.vue';
import type { Template, TemplateInstance } from '@/types/templates';

const route = useRoute();
const store = useTemplatesStore();
const template = ref<Template | null>(null);
const showAdd = ref(false);
const rotateTarget = ref<TemplateInstance | null>(null);
const logsTarget = ref<TemplateInstance | null>(null);
const slug = computed(() => route.params.slug as string);

const instances = computed(() => store.instances.filter(i => i.template_slug === slug.value));

async function refresh() {
  template.value = await templatesApi.get(slug.value);
  await store.loadInstances(slug.value);
}

onMounted(refresh);
watchEffect(() => {
  if (slug.value) refresh();
});

function onCreated(_inst: TemplateInstance) {
  showAdd.value = false;
  refresh();
}

async function onRestart(inst: TemplateInstance) {
  await store.restartInstance(inst.id);
  setTimeout(refresh, 1500); // give the runner a moment
}

async function onDelete(inst: TemplateInstance) {
  if (!confirm(`Delete instance "${inst.name}"? This is irreversible.`)) return;
  await store.deleteInstance(inst.id);
}

function onRotate(inst: TemplateInstance) {
  rotateTarget.value = inst;
}

function onLogs(inst: TemplateInstance) {
  logsTarget.value = inst;
}

async function onRotated() {
  rotateTarget.value = null;
  refresh();
}
</script>
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/templates/TemplateInstanceCard.vue apps-microservices/mcp-gateway-frontend/src/views/TemplateDetailView.vue
git commit -m "feat(mcp-gateway-frontend): add TemplateDetailView + InstanceCard"
```

### Task 26: AddInstanceModal

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/components/templates/AddInstanceModal.vue`

- [ ] **Step 1: Implement**

```vue
<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <h2>Add {{ template.name }} instance</h2>
      <form @submit.prevent="submit">
        <label>
          Name
          <input v-model="name" required maxlength="255" />
        </label>

        <label>
          Service account JSON
          <input type="file" accept="application/json,.json" @change="onFile" required />
        </label>
        <p v-if="fileInfo" class="ok">✓ {{ fileInfo }}</p>
        <p v-if="fileError" class="error">{{ fileError }}</p>

        <fieldset v-if="template.required_extra_env?.length">
          <legend>Required env</legend>
          <label v-for="field in template.required_extra_env" :key="field.key">
            {{ field.label }} <code>({{ field.key }})</code>
            <input v-model="extraEnv[field.key]" :required="field.required" />
          </label>
        </fieldset>

        <p v-if="submitError" class="error">{{ submitError }}</p>

        <div class="actions">
          <button type="button" @click="$emit('close')">Cancel</button>
          <button type="submit" :disabled="!canSubmit">
            {{ submitting ? 'Creating…' : 'Create instance' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useTemplatesStore } from '@/stores/templates';
import type { Template, TemplateInstance } from '@/types/templates';

const props = defineProps<{ template: Template }>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', inst: TemplateInstance): void;
}>();

const store = useTemplatesStore();
const name = ref('');
const extraEnv = reactive<Record<string, string>>({});
const file = ref<File | null>(null);
const fileInfo = ref('');
const fileError = ref('');
const submitError = ref('');
const submitting = ref(false);

const canSubmit = computed(() =>
  !!name.value && !!file.value && !fileError.value && !submitting.value
);

function onFile(e: Event) {
  const target = e.target as HTMLInputElement;
  const f = target.files?.[0] ?? null;
  file.value = f;
  fileInfo.value = '';
  fileError.value = '';
  if (!f) return;
  if (f.size > 16 * 1024) {
    fileError.value = 'File too large (max 16 KB)';
    return;
  }
  f.text().then(text => {
    try {
      const j = JSON.parse(text);
      if (j.type !== 'service_account') {
        fileError.value = `type is ${j.type}, expected service_account`;
        return;
      }
      if (!j.client_email) {
        fileError.value = 'client_email missing';
        return;
      }
      fileInfo.value = j.client_email;
    } catch {
      fileError.value = 'not valid JSON';
    }
  });
}

async function submit() {
  if (!file.value) return;
  submitting.value = true;
  submitError.value = '';
  try {
    const inst = await store.createInstance({
      template_slug: props.template.slug,
      name: name.value,
      extra_env: Object.keys(extraEnv).length ? { ...extraEnv } : undefined,
      credentials: file.value,
    });
    emit('created', inst);
  } catch (e: any) {
    submitError.value = e?.response?.data?.error ?? e.message;
  } finally {
    submitting.value = false;
  }
}
</script>
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/templates/AddInstanceModal.vue
git commit -m "feat(mcp-gateway-frontend): add AddInstanceModal with client-side SA JSON validation"
```

### Task 27: RotateCredentialsModal + InstanceLogsModal

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/components/templates/RotateCredentialsModal.vue`
- Create: `apps-microservices/mcp-gateway-frontend/src/components/templates/InstanceLogsModal.vue`

- [ ] **Step 1: RotateCredentialsModal (similar to AddInstanceModal but name is pre-filled, template read-only)**

```vue
<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <h2>Rotate credentials — {{ instance.name }}</h2>
      <p>Upload a new service-account JSON. The instance will be respawned with the new credentials. The old JSON is discarded.</p>
      <form @submit.prevent="submit">
        <input type="file" accept="application/json,.json" @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null" required />
        <p v-if="error" class="error">{{ error }}</p>
        <div class="actions">
          <button type="button" @click="$emit('close')">Cancel</button>
          <button type="submit" :disabled="!file || submitting">{{ submitting ? 'Rotating…' : 'Rotate' }}</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useTemplatesStore } from '@/stores/templates';
import type { TemplateInstance } from '@/types/templates';

const props = defineProps<{ instance: TemplateInstance }>();
const emit = defineEmits<{ (e: 'close' | 'rotated'): void }>();

const store = useTemplatesStore();
const file = ref<File | null>(null);
const error = ref('');
const submitting = ref(false);

async function submit() {
  if (!file.value) return;
  submitting.value = true;
  try {
    await store.rotateCredentials(props.instance.id, file.value);
    emit('rotated');
  } catch (e: any) {
    error.value = e?.response?.data?.error ?? e.message;
  } finally {
    submitting.value = false;
  }
}
</script>
```

- [ ] **Step 2: InstanceLogsModal**

```vue
<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal wide">
      <h2>Logs — {{ instance.name }}</h2>
      <pre class="stderr">{{ stderr || 'No logs yet' }}</pre>
      <button @click="$emit('close')">Close</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { templatesApi } from '@/api/templates';
import type { TemplateInstance } from '@/types/templates';

const props = defineProps<{ instance: TemplateInstance }>();
defineEmits<{ (e: 'close'): void }>();

const stderr = ref('');
onMounted(async () => {
  const fresh = await templatesApi.getInstance(props.instance.id);
  stderr.value = fresh.stderr_tail ?? '';
});
</script>

<style scoped>
.modal.wide { max-width: 900px; }
.stderr { font-family: ui-monospace, monospace; font-size: 0.85em; background: #111; color: #ccc; padding: 12px; border-radius: 6px; max-height: 60vh; overflow: auto; white-space: pre-wrap; }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/templates/
git commit -m "feat(mcp-gateway-frontend): add rotate + logs modals"
```

---

## Phase 18 — End-to-end smoke test

### Task 28: Manual E2E checklist

**No code change — verification only.**

- [ ] **Step 1: Bring up the stack**

```bash
docker compose --profile mcp up -d mcp-gateway-service mcp-google-templates-runner mysql
docker compose logs -f mcp-google-templates-runner
```

Expected: runner logs `startup sync: 0 desired instances` (or the count if you reboot with existing rows).

- [ ] **Step 2: Generate a test service-account JSON**

Download a real GA4 SA key from GCP, or create a dummy with a real-looking `private_key` PEM for validation-path testing:

```bash
# Minimal validity-pass JSON (not usable against Google, just passes gateway validation)
cat > /tmp/fake-sa.json <<'EOF'
{
  "type": "service_account",
  "project_id": "test-project",
  "client_email": "test@test-project.iam.gserviceaccount.com",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...fake...\n-----END PRIVATE KEY-----\n"
}
EOF
```

- [ ] **Step 3: Browser flow**

Navigate to `http://localhost:<frontend-port>/admin/templates`. You should see GA + GSC listed with 0 instances each.

Click GA → **+ Add instance** → name "smoke test" → upload the JSON → set `GOOGLE_PROJECT_ID=test-project` → submit.

Expected: the instance card appears with `pending` badge, transitioning to either `running` (if the upstream package accepts the credentials) or `failed` (most likely with a dummy key — click View logs to see the upstream error).

- [ ] **Step 4: Verify gateway DB state**

```bash
docker compose exec mysql mysql -u root -p<pw> mcp_gateway -e \
  "SELECT id, name, runner_status, runner_port FROM template_instances; SELECT id, url, health_status FROM mcp_servers WHERE id IN (SELECT mcp_server_id FROM template_instances);"
```

Expected: one `template_instances` row, one matching `mcp_servers` row with a non-placeholder URL.

- [ ] **Step 5: Verify runner state**

```bash
docker compose exec mcp-google-templates-runner curl -s -H "X-Admin-Token: <token>" http://localhost:8590/admin/instances | jq
```

Expected: one instance listed with `status: running` or `failed` + stderr tail.

- [ ] **Step 6: Independent-lifecycle check**

Kill just that one subprocess inside the runner:

```bash
docker compose exec mcp-google-templates-runner sh -c 'kill $(pgrep -f analytics-mcp)'
```

Watch the logs: supervisor detects exit, sleeps 1s, respawns. Other running instances (if any) are untouched. Gateway status eventually shows `running` again after the next poll.

- [ ] **Step 7: Delete**

From the UI, delete the instance. Verify:

```bash
docker compose exec mysql mysql -u root -p<pw> mcp_gateway -e "SELECT COUNT(*) FROM template_instances; SELECT COUNT(*) FROM mcp_servers WHERE id LIKE '%';"
```

Expected: row deleted, `mcp_servers` row gone too, subprocess gone from runner listing, tmpfs JSON gone.

- [ ] **Step 8: Runner restart preserves state**

Add a new instance. Restart the runner container. The gateway should continue to register the instance, and after the runner's startup sync the subprocess should respawn within a few seconds.

```bash
docker compose restart mcp-google-templates-runner
docker compose logs mcp-google-templates-runner --tail 30
```

Expected: `startup sync: N desired instances`, followed by spawn messages.

---

## Phase 19 — Documentation

### Task 29: Update CLAUDE.md files

**Files:**
- Modify: `CLAUDE.md` (root)
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Root CLAUDE.md — add the new service to the service map table**

Under `## Service Map`, insert a row:

```
| MCP Template Runner | `mcp-google-templates-runner` | Python / FastAPI | Local OK |
```

- [ ] **Step 2: Gateway CLAUDE.md — add env vars, new tables, new endpoints**

Append to the `## Environment Variables` table:

```
| `GOOGLE_TEMPLATES_RUNNER_URL` | — | Base URL of the templates runner sidecar |
| `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` | — | Shared secret for the runner admin API |
```

Update the `## Database` table to list `templates` and `template_instances`:

```
| `templates` | Template catalog (seed: ga, gsc) |
| `template_instances` | One row per admin-uploaded SA JSON |
```

Add under `## API Endpoints`:

```
### Template Catalog (`/api/v1/`)
- `GET /templates` — list available templates
- `GET /templates/{slug}` — template detail
- `GET/POST /template-instances` — list / create instance
- `GET/DELETE /template-instances/{id}` — detail / remove
- `POST /template-instances/{id}/restart` — respawn subprocess
- `POST /template-instances/{id}/rotate-credentials` — upload new SA JSON

### Runner Sync (internal, shared-secret auth)
- `POST /api/v1/internal/runner/sync` — runner's startup/reconcile pull
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "docs: document Google templates feature in CLAUDE.md"
```

---

## Self-Review Checklist

After completing all tasks, verify:

- [ ] **Spec coverage.** Cross-reference each section of `docs/superpowers/specs/2026-04-17-google-templates-dynamic-secrets-design.md` against the tasks above. Every requirement has at least one task.
- [ ] **All tests pass** in both services:
  ```bash
  cd apps-microservices/mcp-gateway-service && go test ./...
  cd apps-microservices/mcp-google-templates-runner && pytest
  ```
- [ ] **Build green**: `docker compose --profile mcp build mcp-gateway-service mcp-google-templates-runner`
- [ ] **E2E smoke (Task 28)** passes end-to-end with a real GA SA key in staging.
- [ ] **No secrets in logs**: grep gateway + runner logs for SA JSON fragments after a create+delete cycle.
- [ ] **`docs/superpowers/specs/...-design.md`** still matches reality — if anything diverged, amend the spec.

---

## Plan size

~29 tasks, each ~3–8 steps, most with real code. Estimated effort: 8–14 focused hours, depending on tooling friction (Docker networking, flaky MySQL startup, first-time Vue familiarity).
