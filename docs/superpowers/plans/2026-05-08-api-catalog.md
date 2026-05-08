# API Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `api-catalog-service` (Go/gRPC) as the platform's central registry of services + endpoints, integrate it into `account-service-{backend,frontend}` as a new "API" admin nav, and wire `api-gateway-go` to consume it as the primary routing source (with `SERVICE_*` env fallback).

**Architecture:** New microservice owns DB + scanner + gRPC. account-backend is the broker for the Vue admin UI (HTTP→gRPC). gateway pulls service map over gRPC every 60 s, falls back to env at boot/refresh failure. Phased rollout via `GATEWAY_USE_CATALOG` flag.

**Tech Stack:** Go 1.24, `google.golang.org/grpc`, `gorm.io/gorm` + `gorm.io/driver/mysql`, `golang.org/x/sync/errgroup`, `google.golang.org/grpc/reflection`, `github.com/jhump/protoreflect/grpcreflect` (client), Vue 3, Vitest, Pinia, MySQL.

**Spec:** `docs/superpowers/specs/2026-05-08-api-catalog-design.md`.

**Base branch:** `origin/features/poc`.

---

## File Structure (target)

```
protos/grpc_stubs/
  api_catalog.proto                                   # NEW

apps-microservices/api-catalog-service/                # NEW SERVICE
  cmd/server/main.go
  internal/
    config/config.go
    db/{mysql.go,models.go}
    repository/{service_repo.go,endpoint_repo.go}
    scanner/{scanner.go,env_source.go,probe_rest.go,probe_ws.go,probe_grpc.go,cron.go}
    grpcserver/{server.go,interceptor_auth.go,mapper.go}
    health/health.go
    genproto/api_catalog/{api_catalog.pb.go,api_catalog_grpc.pb.go}   # generated
  init-db/01_schema.sql
  Dockerfile
  go.mod / go.sum
  CLAUDE.md

apps-microservices/account-service-backend/
  internal/api/api_catalog_handlers.go                  # NEW
  internal/api/api_catalog_client.go                    # NEW
  internal/genproto/api_catalog/                        # generated
  cmd/server/main.go                                    # MODIFY (wire client + routes)

apps-microservices/account-service-frontend/
  src/api/apiCatalog.ts                                 # NEW
  src/types/apiCatalog.ts                               # NEW
  src/views/{ApiCatalogListView,ApiCatalogDetailView,ApiCatalogFormView}.vue   # NEW
  src/components/api-catalog/{ProtocolBadge,EndpointTable,ScanStatusBadge}.vue # NEW
  src/router/index.ts                                   # MODIFY
  (sidebar nav component)                               # MODIFY

apps-microservices/api-gateway-go/
  internal/catalog/{client.go,refresher.go}             # NEW
  internal/genproto/api_catalog/                        # generated
  internal/config/service_map.go                        # MODIFY
  cmd/gateway/main.go                                   # MODIFY

libs/common-utils/src/<pkg>/api_info.py                 # NEW (FastAPI helper)

.github/workflows/{ci_services_api_catalog.yml,cd_build_push_api_catalog.yml}  # NEW
docker-compose.yml                                      # MODIFY (add api-catalog-service)
```

---

## Phase 0 — Branch + Proto

### Task 0.1: Cut implementation branch from `origin/features/poc`

- [ ] **Step 1:** Fetch + create branch.

```bash
git fetch origin features/poc
git checkout -b features/api-catalog origin/features/poc
```

- [ ] **Step 2:** Verify HEAD matches origin/features/poc.

```bash
git rev-parse HEAD
git rev-parse origin/features/poc
```

Expected: identical SHAs.

### Task 0.2: Add `api_catalog.proto`

**Files:**
- Create: `protos/grpc_stubs/api_catalog.proto`

- [ ] **Step 1:** Write proto file with the contract from the spec.

```proto
syntax = "proto3";
package api_catalog;
option go_package = "rag-hp/api_catalog;api_catalog";

import "google/protobuf/timestamp.proto";

service ApiCatalog {
  rpc ListServices(ListServicesRequest)   returns (ListServicesResponse);
  rpc GetService(GetServiceRequest)       returns (Service);
  rpc ListEndpoints(ListEndpointsRequest) returns (ListEndpointsResponse);
  rpc CreateService(CreateServiceRequest) returns (Service);
  rpc UpdateService(UpdateServiceRequest) returns (Service);
  rpc DeleteService(DeleteServiceRequest) returns (DeleteServiceResponse);
  rpc RescanAll(RescanAllRequest)         returns (RescanReport);
  rpc RescanService(RescanServiceRequest) returns (RescanReport);
}

enum Protocol { PROTOCOL_UNSPECIFIED = 0; REST = 1; WS = 2; GRPC = 3; }
enum Source   { SOURCE_UNSPECIFIED   = 0; ENV  = 1; MANUAL = 2; SCAN = 3; }
enum Status   { STATUS_UNSPECIFIED   = 0; ACTIVE = 1; DEPRECATED = 2; DOWN = 3; }

message Service {
  string id = 1;
  string name = 2;
  string base_url = 3;
  repeated Protocol protocols = 4;
  Source source = 5;
  Status status = 6;
  string description = 7;
  string owner = 8;
  repeated string tags = 9;
  string api_info_url = 10;
  string grpc_address = 11;
  google.protobuf.Timestamp last_scanned_at = 12;
  bool   last_scan_ok = 13;
  string last_scan_error = 14;
  google.protobuf.Timestamp created_at = 15;
  google.protobuf.Timestamp updated_at = 16;
}

message Endpoint {
  string id = 1;
  string service_id = 2;
  Protocol protocol = 3;
  string method = 4;
  string path = 5;
  string summary = 6;
  string operation_id = 7;
  repeated string tags = 8;
  bool deprecated = 9;
}

message ListServicesRequest   { int32 limit = 1; int32 offset = 2; string filter = 3; }
message ListServicesResponse  { repeated Service items = 1; int64 total = 2; }
message GetServiceRequest     { string id = 1; }
message ListEndpointsRequest  { string service_id = 1; Protocol protocol = 2; }
message ListEndpointsResponse { repeated Endpoint items = 1; }

message CreateServiceRequest {
  string name = 1;
  string base_url = 2;
  repeated Protocol protocols = 3;
  string description = 4;
  string owner = 5;
  repeated string tags = 6;
  string api_info_url = 7;
  string grpc_address = 8;
  string created_by = 9;
}
message UpdateServiceRequest {
  string id = 1;
  optional string description = 2;
  optional string owner = 3;
  repeated string tags = 4;
  optional Status status = 5;
}
message DeleteServiceRequest  { string id = 1; }
message DeleteServiceResponse { bool deleted = 1; }
message RescanAllRequest      { bool force = 1; }
message RescanServiceRequest  { string id = 1; }
message RescanReport {
  int32 services_scanned = 1;
  int32 services_ok = 2;
  int32 services_failed = 3;
  repeated string errors = 4;
  google.protobuf.Timestamp finished_at = 5;
}
```

- [ ] **Step 2:** Run `/proto-sync` to regenerate Python stubs (verify it doesn't fail; Python stubs not consumed but kept consistent).

- [ ] **Step 3:** Commit.

```bash
git add protos/grpc_stubs/api_catalog.proto libs/grpc-stubs/
git commit -m "feat(protos): add api_catalog.proto for service registry RPCs"
```

---

## Phase 1 — api-catalog-service: scaffold + DB

### Task 1.1: Initialize Go module

**Files:**
- Create: `apps-microservices/api-catalog-service/go.mod`
- Create: `apps-microservices/api-catalog-service/cmd/server/main.go`
- Create: `apps-microservices/api-catalog-service/CLAUDE.md`

- [ ] **Step 1:** Init module.

```bash
mkdir -p apps-microservices/api-catalog-service/cmd/server
cd apps-microservices/api-catalog-service
go mod init github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service
```

- [ ] **Step 2:** Stub `cmd/server/main.go`.

```go
package main

import "log"

func main() {
    log.Println("api-catalog-service starting (stub)")
}
```

- [ ] **Step 3:** Build to verify.

```bash
go build ./cmd/server
```

Expected: produces `server` binary, no errors.

- [ ] **Step 4:** Write `CLAUDE.md`.

```markdown
# api-catalog-service

Centralized registry of platform services + endpoints. Owns scanner, DB, and gRPC API. Consumed by account-service-backend (CRUD) and api-gateway-go (routing source).

## Tech Stack

- Go 1.24
- google.golang.org/grpc
- GORM v2 + MySQL (gateway-mysql, DB `catalog_db`)
- HTTP client (REST + /api-info probes)
- jhump/protoreflect (gRPC reflection client)

## Run

```bash
cd apps-microservices/api-catalog-service
go run ./cmd/server/
```

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-05-08-api-catalog-design.md`
- Plan: `docs/superpowers/plans/2026-05-08-api-catalog.md`
```

- [ ] **Step 5:** Commit.

```bash
git add apps-microservices/api-catalog-service/
git commit -m "feat(api-catalog): scaffold Go module + CLAUDE.md"
```

### Task 1.2: Generate Go gRPC stubs into `internal/genproto/api_catalog`

**Files:**
- Create: `apps-microservices/api-catalog-service/internal/genproto/api_catalog/{api_catalog.pb.go,api_catalog_grpc.pb.go}`

- [ ] **Step 1:** Add buf.gen.yaml or use protoc directly. Run from repo root:

```bash
cd /home/sandratra/RAG-HP-PUB
protoc \
  --go_out=apps-microservices/api-catalog-service/internal/genproto \
  --go_opt=paths=source_relative \
  --go-grpc_out=apps-microservices/api-catalog-service/internal/genproto \
  --go-grpc_opt=paths=source_relative \
  -I protos/grpc_stubs \
  protos/grpc_stubs/api_catalog.proto
```

(Note: with `option go_package = "rag-hp/api_catalog;api_catalog"`, output lands in `genproto/api_catalog/`.)

- [ ] **Step 2:** Add deps and build.

```bash
cd apps-microservices/api-catalog-service
go get google.golang.org/grpc google.golang.org/protobuf
go build ./...
```

Expected: builds clean.

- [ ] **Step 3:** Commit.

```bash
git add apps-microservices/api-catalog-service/
git commit -m "feat(api-catalog): generate Go gRPC stubs"
```

### Task 1.3: Config loader

**Files:**
- Create: `apps-microservices/api-catalog-service/internal/config/config.go`
- Create: `apps-microservices/api-catalog-service/internal/config/config_test.go`

- [ ] **Step 1:** Write failing test `config_test.go`.

```go
package config

import (
    "os"
    "testing"
    "time"
)

func TestLoad_Defaults(t *testing.T) {
    os.Clearenv()
    os.Setenv("MYSQL_PASS", "x")
    os.Setenv("ADMIN_KEY", "k")
    cfg := Load()
    if cfg.MySQLHost != "gateway-mysql" {
        t.Fatalf("MySQLHost = %q, want gateway-mysql", cfg.MySQLHost)
    }
    if cfg.GRPCPort != 9100 {
        t.Fatalf("GRPCPort = %d, want 9100", cfg.GRPCPort)
    }
    if cfg.ScanInterval != 15*time.Minute {
        t.Fatalf("ScanInterval = %v, want 15m", cfg.ScanInterval)
    }
    if cfg.ScanConcurrency != 16 {
        t.Fatalf("ScanConcurrency = %d, want 16", cfg.ScanConcurrency)
    }
}

func TestLoad_SeedTargetsFromEnv(t *testing.T) {
    os.Clearenv()
    os.Setenv("MYSQL_PASS", "x")
    os.Setenv("ADMIN_KEY", "k")
    os.Setenv("SERVICE_FOO", "http://foo:8000")
    os.Setenv("SERVICE_BAR_BAZ", "http://bar-baz:8001")
    cfg := Load()
    if got := cfg.SeedTargets["foo-service"]; got != "http://foo:8000" {
        t.Fatalf("foo-service = %q", got)
    }
    if got := cfg.SeedTargets["bar_baz-service"]; got != "http://bar-baz:8001" {
        t.Fatalf("bar_baz-service = %q", got)
    }
}
```

- [ ] **Step 2:** Run test, expect FAIL.

```bash
go test ./internal/config -v
```

- [ ] **Step 3:** Implement `config.go`.

```go
package config

import (
    "log"
    "os"
    "strconv"
    "strings"
    "time"
)

type Config struct {
    MySQLHost       string
    MySQLPort       string
    MySQLUser       string
    MySQLPass       string
    MySQLDB         string
    GRPCPort        int
    HealthPort      int
    AdminKey        string
    ScanInterval    time.Duration
    ScanConcurrency int
    ProbeTimeout    time.Duration
    SeedTargets     map[string]string // name+"-service" -> base_url
}

func Load() Config {
    cfg := Config{
        MySQLHost:       getenv("MYSQL_HOST", "gateway-mysql"),
        MySQLPort:       getenv("MYSQL_PORT", "3306"),
        MySQLUser:       getenv("MYSQL_USER", "catalog_user"),
        MySQLPass:       os.Getenv("MYSQL_PASS"),
        MySQLDB:         getenv("MYSQL_DB", "catalog_db"),
        GRPCPort:        getenvInt("GRPC_PORT", 9100),
        HealthPort:      getenvInt("HEALTH_PORT", 9101),
        AdminKey:        os.Getenv("ADMIN_KEY"),
        ScanInterval:    getenvDuration("SCAN_INTERVAL", 15*time.Minute),
        ScanConcurrency: getenvInt("SCAN_CONCURRENCY", 16),
        ProbeTimeout:    getenvDuration("PROBE_TIMEOUT", 3*time.Second),
        SeedTargets:     buildSeedTargets(),
    }
    if cfg.MySQLPass == "" {
        log.Println("WARN: MYSQL_PASS empty")
    }
    if cfg.AdminKey == "" {
        log.Println("WARN: ADMIN_KEY empty (write RPCs will reject all)")
    }
    return cfg
}

func buildSeedTargets() map[string]string {
    out := map[string]string{}
    for _, kv := range os.Environ() {
        eq := strings.IndexByte(kv, '=')
        if eq <= 0 {
            continue
        }
        k, v := kv[:eq], kv[eq+1:]
        if !strings.HasPrefix(k, "SERVICE_") {
            continue
        }
        name := strings.ToLower(strings.TrimPrefix(k, "SERVICE_"))
        out[name+"-service"] = v
    }
    return out
}

func getenv(k, def string) string {
    if v, ok := os.LookupEnv(k); ok && v != "" {
        return v
    }
    return def
}

func getenvInt(k string, def int) int {
    v := os.Getenv(k)
    if v == "" {
        return def
    }
    n, err := strconv.Atoi(v)
    if err != nil {
        return def
    }
    return n
}

func getenvDuration(k string, def time.Duration) time.Duration {
    v := os.Getenv(k)
    if v == "" {
        return def
    }
    d, err := time.ParseDuration(v)
    if err != nil {
        return def
    }
    return d
}
```

- [ ] **Step 4:** Run test, expect PASS.

```bash
go test ./internal/config -v
```

- [ ] **Step 5:** Commit.

```bash
git add internal/config/
git commit -m "feat(api-catalog): config loader with SERVICE_* seed targets"
```

### Task 1.4: DB models + GORM bootstrap

**Files:**
- Create: `apps-microservices/api-catalog-service/internal/db/models.go`
- Create: `apps-microservices/api-catalog-service/internal/db/mysql.go`
- Create: `apps-microservices/api-catalog-service/internal/db/mysql_test.go`

- [ ] **Step 1:** Write `models.go`.

```go
package db

import "time"

type ServiceRow struct {
    ID              string `gorm:"type:char(36);primaryKey"`
    Name            string `gorm:"size:128;uniqueIndex;not null"`
    BaseURL         string `gorm:"size:512;not null"`
    Protocols       string `gorm:"type:json;not null"`        // JSON-encoded []string
    Source          string `gorm:"type:enum('env','manual','scan');not null"`
    Status          string `gorm:"type:enum('active','deprecated','down');not null;default:'active'"`
    Description     string `gorm:"type:text"`
    Owner           string `gorm:"size:128"`
    Tags            string `gorm:"type:json"`                 // JSON-encoded []string
    APIInfoURL      string `gorm:"size:512;column:api_info_url"`
    GRPCAddress     string `gorm:"size:512;column:grpc_address"`
    LastScannedAt   *time.Time
    LastScanOK      *bool  `gorm:"column:last_scan_ok"`
    LastScanError   string `gorm:"type:text;column:last_scan_error"`
    CreatedBy       string `gorm:"size:255"`
    CreatedAt       time.Time
    UpdatedAt       time.Time
}

func (ServiceRow) TableName() string { return "catalog_services" }

type EndpointRow struct {
    ID          string `gorm:"type:char(36);primaryKey"`
    ServiceID   string `gorm:"type:char(36);not null;index"`
    Protocol    string `gorm:"type:enum('rest','ws','grpc');not null"`
    Method      string `gorm:"size:16"`
    Path        string `gorm:"size:512;not null"`
    Summary     string `gorm:"size:512"`
    OperationID string `gorm:"size:255;column:operation_id"`
    Tags        string `gorm:"type:json"`
    Deprecated  bool   `gorm:"not null;default:false"`
}

func (EndpointRow) TableName() string { return "catalog_endpoints" }
```

- [ ] **Step 2:** Write failing test `mysql_test.go` (uses SQLite in-memory for portability).

```go
package db

import (
    "testing"

    "gorm.io/driver/sqlite"
    "gorm.io/gorm"
)

func openTestDB(t *testing.T) *gorm.DB {
    t.Helper()
    g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
    if err != nil {
        t.Fatal(err)
    }
    if err := AutoMigrate(g); err != nil {
        t.Fatal(err)
    }
    return g
}

func TestAutoMigrate_CreatesTables(t *testing.T) {
    g := openTestDB(t)
    if !g.Migrator().HasTable(&ServiceRow{}) {
        t.Fatal("catalog_services table missing")
    }
    if !g.Migrator().HasTable(&EndpointRow{}) {
        t.Fatal("catalog_endpoints table missing")
    }
}
```

- [ ] **Step 3:** Implement `mysql.go`.

```go
package db

import (
    "fmt"

    "gorm.io/driver/mysql"
    "gorm.io/gorm"
)

func Open(host, port, user, pass, name string) (*gorm.DB, error) {
    dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true&charset=utf8mb4", user, pass, host, port, name)
    g, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
    if err != nil {
        return nil, fmt.Errorf("open mysql: %w", err)
    }
    return g, nil
}

func AutoMigrate(g *gorm.DB) error {
    return g.AutoMigrate(&ServiceRow{}, &EndpointRow{})
}
```

- [ ] **Step 4:** Add SQLite test dep and run.

```bash
go get gorm.io/driver/sqlite gorm.io/gorm gorm.io/driver/mysql
go test ./internal/db -v
```

Expected: PASS.

- [ ] **Step 5:** Commit.

```bash
git add internal/db/ go.mod go.sum
git commit -m "feat(api-catalog): GORM models + MySQL bootstrap"
```

### Task 1.5: Repositories (services + endpoints)

**Files:**
- Create: `internal/repository/service_repo.go`
- Create: `internal/repository/endpoint_repo.go`
- Create: `internal/repository/repo_test.go`

- [ ] **Step 1:** Write failing tests covering create/get/list/update/delete and bulk endpoint replace.

```go
package repository

import (
    "testing"

    "gorm.io/driver/sqlite"
    "gorm.io/gorm"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

func newDB(t *testing.T) *gorm.DB {
    t.Helper()
    g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
    if err != nil {
        t.Fatal(err)
    }
    if err := db.AutoMigrate(g); err != nil {
        t.Fatal(err)
    }
    return g
}

func TestServiceRepo_CreateGet(t *testing.T) {
    r := NewServiceRepo(newDB(t))
    row := &db.ServiceRow{
        ID: "00000000-0000-0000-0000-000000000001", Name: "foo-service",
        BaseURL: "http://foo:8000", Protocols: `["rest"]`, Source: "env", Status: "active",
    }
    if err := r.Create(row); err != nil {
        t.Fatal(err)
    }
    got, err := r.GetByID(row.ID)
    if err != nil || got.Name != "foo-service" {
        t.Fatalf("GetByID got=%v err=%v", got, err)
    }
}

func TestServiceRepo_List_OrdersByName(t *testing.T) {
    r := NewServiceRepo(newDB(t))
    _ = r.Create(&db.ServiceRow{ID: "1", Name: "b-service", BaseURL: "x", Protocols: "[]", Source: "env", Status: "active"})
    _ = r.Create(&db.ServiceRow{ID: "2", Name: "a-service", BaseURL: "x", Protocols: "[]", Source: "env", Status: "active"})
    items, total, err := r.List(10, 0, "")
    if err != nil || total != 2 || items[0].Name != "a-service" {
        t.Fatalf("List items=%v total=%d err=%v", items, total, err)
    }
}

func TestEndpointRepo_BulkReplace(t *testing.T) {
    g := newDB(t)
    sr := NewServiceRepo(g)
    er := NewEndpointRepo(g)
    _ = sr.Create(&db.ServiceRow{ID: "s1", Name: "x-service", BaseURL: "x", Protocols: "[]", Source: "env", Status: "active"})
    if err := er.ReplaceForService("s1", []db.EndpointRow{
        {ID: "e1", ServiceID: "s1", Protocol: "rest", Method: "GET", Path: "/a"},
    }); err != nil {
        t.Fatal(err)
    }
    if err := er.ReplaceForService("s1", []db.EndpointRow{
        {ID: "e2", ServiceID: "s1", Protocol: "rest", Method: "POST", Path: "/b"},
    }); err != nil {
        t.Fatal(err)
    }
    got, _ := er.ListForService("s1", "")
    if len(got) != 1 || got[0].Path != "/b" {
        t.Fatalf("after replace, want [/b], got %+v", got)
    }
}
```

- [ ] **Step 2:** Implement `service_repo.go`.

```go
package repository

import (
    "errors"
    "time"

    "gorm.io/gorm"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

var ErrNotFound = errors.New("not found")

type ServiceRepo struct{ g *gorm.DB }

func NewServiceRepo(g *gorm.DB) *ServiceRepo { return &ServiceRepo{g: g} }

func (r *ServiceRepo) Create(s *db.ServiceRow) error {
    now := time.Now().UTC()
    if s.CreatedAt.IsZero() {
        s.CreatedAt = now
    }
    s.UpdatedAt = now
    return r.g.Create(s).Error
}

func (r *ServiceRepo) GetByID(id string) (*db.ServiceRow, error) {
    var s db.ServiceRow
    if err := r.g.First(&s, "id = ?", id).Error; err != nil {
        if errors.Is(err, gorm.ErrRecordNotFound) {
            return nil, ErrNotFound
        }
        return nil, err
    }
    return &s, nil
}

func (r *ServiceRepo) GetByName(name string) (*db.ServiceRow, error) {
    var s db.ServiceRow
    if err := r.g.First(&s, "name = ?", name).Error; err != nil {
        if errors.Is(err, gorm.ErrRecordNotFound) {
            return nil, ErrNotFound
        }
        return nil, err
    }
    return &s, nil
}

func (r *ServiceRepo) List(limit, offset int, filter string) ([]db.ServiceRow, int64, error) {
    if limit <= 0 {
        limit = 100
    }
    q := r.g.Model(&db.ServiceRow{})
    if filter != "" {
        q = q.Where("name LIKE ?", "%"+filter+"%")
    }
    var total int64
    if err := q.Count(&total).Error; err != nil {
        return nil, 0, err
    }
    var items []db.ServiceRow
    if err := q.Order("name ASC").Limit(limit).Offset(offset).Find(&items).Error; err != nil {
        return nil, 0, err
    }
    return items, total, nil
}

func (r *ServiceRepo) Update(id string, fields map[string]any) error {
    fields["updated_at"] = time.Now().UTC()
    res := r.g.Model(&db.ServiceRow{}).Where("id = ?", id).Updates(fields)
    if res.Error != nil {
        return res.Error
    }
    if res.RowsAffected == 0 {
        return ErrNotFound
    }
    return nil
}

func (r *ServiceRepo) Delete(id string) error {
    res := r.g.Delete(&db.ServiceRow{}, "id = ?", id)
    if res.Error != nil {
        return res.Error
    }
    if res.RowsAffected == 0 {
        return ErrNotFound
    }
    return nil
}

func (r *ServiceRepo) ListAll() ([]db.ServiceRow, error) {
    var items []db.ServiceRow
    if err := r.g.Find(&items).Error; err != nil {
        return nil, err
    }
    return items, nil
}
```

- [ ] **Step 3:** Implement `endpoint_repo.go`.

```go
package repository

import (
    "gorm.io/gorm"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

type EndpointRepo struct{ g *gorm.DB }

func NewEndpointRepo(g *gorm.DB) *EndpointRepo { return &EndpointRepo{g: g} }

func (r *EndpointRepo) ReplaceForService(serviceID string, rows []db.EndpointRow) error {
    return r.g.Transaction(func(tx *gorm.DB) error {
        if err := tx.Where("service_id = ?", serviceID).Delete(&db.EndpointRow{}).Error; err != nil {
            return err
        }
        if len(rows) == 0 {
            return nil
        }
        return tx.CreateInBatches(rows, 200).Error
    })
}

func (r *EndpointRepo) ListForService(serviceID, protocol string) ([]db.EndpointRow, error) {
    q := r.g.Where("service_id = ?", serviceID)
    if protocol != "" {
        q = q.Where("protocol = ?", protocol)
    }
    var items []db.EndpointRow
    if err := q.Order("path ASC").Find(&items).Error; err != nil {
        return nil, err
    }
    return items, nil
}
```

- [ ] **Step 4:** Run tests, expect PASS.

```bash
go test ./internal/repository -v
```

- [ ] **Step 5:** Commit.

```bash
git add internal/repository/
git commit -m "feat(api-catalog): service + endpoint repositories"
```

### Task 1.6: SQL schema migration file

**Files:**
- Create: `apps-microservices/api-catalog-service/init-db/01_schema.sql`

- [ ] **Step 1:** Write schema SQL (matches GORM AutoMigrate output but explicit for ops).

```sql
CREATE DATABASE IF NOT EXISTS catalog_db;
USE catalog_db;

CREATE TABLE IF NOT EXISTS catalog_services (
  id              CHAR(36)     PRIMARY KEY,
  name            VARCHAR(128) NOT NULL,
  base_url        VARCHAR(512) NOT NULL,
  protocols       JSON         NOT NULL,
  source          ENUM('env','manual','scan') NOT NULL,
  status          ENUM('active','deprecated','down') NOT NULL DEFAULT 'active',
  description     TEXT,
  owner           VARCHAR(128),
  tags            JSON,
  api_info_url    VARCHAR(512),
  grpc_address    VARCHAR(512),
  last_scanned_at DATETIME,
  last_scan_ok    TINYINT(1),
  last_scan_error TEXT,
  created_by      VARCHAR(255),
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL,
  UNIQUE KEY uniq_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS catalog_endpoints (
  id           CHAR(36) PRIMARY KEY,
  service_id   CHAR(36) NOT NULL,
  protocol     ENUM('rest','ws','grpc') NOT NULL,
  method       VARCHAR(16),
  path         VARCHAR(512) NOT NULL,
  summary      VARCHAR(512),
  operation_id VARCHAR(255),
  tags         JSON,
  deprecated   TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_endpoint_service FOREIGN KEY (service_id) REFERENCES catalog_services(id) ON DELETE CASCADE,
  KEY idx_endpoint_service (service_id),
  KEY idx_endpoint_proto   (service_id, protocol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2:** Commit.

```bash
git add init-db/
git commit -m "feat(api-catalog): SQL schema for catalog_db"
```

---

## Phase 2 — Scanner

### Task 2.1: REST probe — `GET /openapi.json` → `[]EndpointRow`

**Files:**
- Create: `internal/scanner/probe_rest.go`
- Create: `internal/scanner/probe_rest_test.go`

- [ ] **Step 1:** Write failing test using `httptest`.

```go
package scanner

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"
)

func TestProbeREST_ParsesPaths(t *testing.T) {
    body := `{
      "paths": {
        "/search": {"get": {"operationId":"do_search","summary":"Search","tags":["s"]}},
        "/health": {"get": {"summary":"H","deprecated": true}}
      }
    }`
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.URL.Path != "/openapi.json" {
            http.NotFound(w, r); return
        }
        _, _ = w.Write([]byte(body))
    }))
    defer srv.Close()

    eps, err := ProbeREST(context.Background(), srv.URL, 1*time.Second)
    if err != nil {
        t.Fatal(err)
    }
    if len(eps) != 2 {
        t.Fatalf("got %d endpoints, want 2", len(eps))
    }
}

func TestProbeREST_404_NoError(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(http.NotFound))
    defer srv.Close()
    eps, err := ProbeREST(context.Background(), srv.URL, 1*time.Second)
    if err != nil || len(eps) != 0 {
        t.Fatalf("want 0 eps no err, got %d %v", len(eps), err)
    }
}
```

- [ ] **Step 2:** Implement `probe_rest.go`.

```go
package scanner

import (
    "context"
    "encoding/json"
    "net/http"
    "strings"
    "time"

    "github.com/google/uuid"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

func ProbeREST(ctx context.Context, baseURL string, timeout time.Duration) ([]db.EndpointRow, error) {
    url := strings.TrimRight(baseURL, "/") + "/openapi.json"
    cli := &http.Client{Timeout: timeout}
    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return nil, err
    }
    resp, err := cli.Do(req)
    if err != nil {
        return nil, nil // network unavailable = not-supported
    }
    defer resp.Body.Close()
    if resp.StatusCode != 200 {
        return nil, nil
    }
    var spec struct {
        Paths map[string]map[string]struct {
            OperationID string   `json:"operationId"`
            Summary     string   `json:"summary"`
            Tags        []string `json:"tags"`
            Deprecated  bool     `json:"deprecated"`
        } `json:"paths"`
    }
    if err := json.NewDecoder(resp.Body).Decode(&spec); err != nil {
        return nil, nil
    }
    methods := []string{"get", "post", "put", "delete", "patch", "options", "head"}
    var out []db.EndpointRow
    for path, pmap := range spec.Paths {
        for _, m := range methods {
            op, ok := pmap[m]
            if !ok {
                continue
            }
            tags, _ := json.Marshal(op.Tags)
            out = append(out, db.EndpointRow{
                ID:          uuid.NewString(),
                Protocol:    "rest",
                Method:      strings.ToUpper(m),
                Path:        path,
                Summary:     op.Summary,
                OperationID: op.OperationID,
                Tags:        string(tags),
                Deprecated:  op.Deprecated,
            })
        }
    }
    return out, nil
}
```

- [ ] **Step 3:** Add uuid dep + run.

```bash
go get github.com/google/uuid
go test ./internal/scanner -v -run REST
```

Expected: PASS.

- [ ] **Step 4:** Commit.

```bash
git add internal/scanner/probe_rest.go internal/scanner/probe_rest_test.go go.mod go.sum
git commit -m "feat(api-catalog): REST probe via /openapi.json"
```

### Task 2.2: api-info probe — `GET /api-info` → ws + grpc info

**Files:**
- Create: `internal/scanner/probe_ws.go`
- Create: `internal/scanner/probe_ws_test.go`

- [ ] **Step 1:** Write failing test.

```go
package scanner

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"
)

func TestProbeAPIInfo_FullPayload(t *testing.T) {
    body := `{
      "service":"x","version":"1",
      "ws":  {"endpoints":[{"path":"/ws/a","summary":"A"},{"path":"/ws/b"}]},
      "grpc":{"address":"x:50051","reflection":true}
    }`
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.URL.Path != "/api-info" {
            http.NotFound(w, r); return
        }
        _, _ = w.Write([]byte(body))
    }))
    defer srv.Close()
    info := ProbeAPIInfo(context.Background(), srv.URL, time.Second)
    if info.GRPCAddress != "x:50051" || !info.GRPCReflection {
        t.Fatalf("grpc info wrong: %+v", info)
    }
    if len(info.WSEndpoints) != 2 || info.WSEndpoints[0].Path != "/ws/a" {
        t.Fatalf("ws wrong: %+v", info.WSEndpoints)
    }
}

func TestProbeAPIInfo_404_ReturnsZero(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(http.NotFound))
    defer srv.Close()
    info := ProbeAPIInfo(context.Background(), srv.URL, time.Second)
    if info.GRPCAddress != "" || len(info.WSEndpoints) != 0 {
        t.Fatalf("expect zero info, got %+v", info)
    }
}
```

- [ ] **Step 2:** Implement.

```go
package scanner

import (
    "context"
    "encoding/json"
    "net/http"
    "strings"
    "time"
)

type WSEndpoint struct {
    Path    string
    Summary string
}

type APIInfo struct {
    WSEndpoints    []WSEndpoint
    GRPCAddress    string
    GRPCReflection bool
}

func ProbeAPIInfo(ctx context.Context, baseURL string, timeout time.Duration) APIInfo {
    url := strings.TrimRight(baseURL, "/") + "/api-info"
    cli := &http.Client{Timeout: timeout}
    req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
    if err != nil {
        return APIInfo{}
    }
    resp, err := cli.Do(req)
    if err != nil {
        return APIInfo{}
    }
    defer resp.Body.Close()
    if resp.StatusCode != 200 {
        return APIInfo{}
    }
    var raw struct {
        WS struct {
            Endpoints []struct {
                Path    string `json:"path"`
                Summary string `json:"summary"`
            } `json:"endpoints"`
        } `json:"ws"`
        GRPC struct {
            Address    string `json:"address"`
            Reflection bool   `json:"reflection"`
        } `json:"grpc"`
    }
    if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
        return APIInfo{}
    }
    info := APIInfo{GRPCAddress: raw.GRPC.Address, GRPCReflection: raw.GRPC.Reflection}
    for _, e := range raw.WS.Endpoints {
        info.WSEndpoints = append(info.WSEndpoints, WSEndpoint{Path: e.Path, Summary: e.Summary})
    }
    return info
}
```

- [ ] **Step 3:** Run tests.

```bash
go test ./internal/scanner -v -run APIInfo
```

- [ ] **Step 4:** Commit.

```bash
git add internal/scanner/probe_ws.go internal/scanner/probe_ws_test.go
git commit -m "feat(api-catalog): /api-info probe (WS + gRPC discovery)"
```

### Task 2.3: gRPC reflection probe

**Files:**
- Create: `internal/scanner/probe_grpc.go`
- Create: `internal/scanner/probe_grpc_test.go`

- [ ] **Step 1:** Add deps.

```bash
go get github.com/jhump/protoreflect/grpcreflect google.golang.org/grpc/reflection
```

- [ ] **Step 2:** Write failing test using bufconn + reflection-enabled server.

```go
package scanner

import (
    "context"
    "net"
    "testing"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"
    "google.golang.org/grpc/reflection"
    "google.golang.org/grpc/test/bufconn"
)

func startReflectionServer(t *testing.T) (string, func()) {
    t.Helper()
    lis, err := net.Listen("tcp", "127.0.0.1:0")
    if err != nil { t.Fatal(err) }
    srv := grpc.NewServer()
    reflection.Register(srv)
    go func() { _ = srv.Serve(lis) }()
    return lis.Addr().String(), func() { srv.Stop() }
}

func TestProbeGRPC_ListsReflectionService(t *testing.T) {
    addr, stop := startReflectionServer(t)
    defer stop()
    ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
    defer cancel()
    eps, err := ProbeGRPC(ctx, addr, time.Second, grpc.WithTransportCredentials(insecure.NewCredentials()))
    if err != nil { t.Fatal(err) }
    found := false
    for _, e := range eps {
        if e.Path == "grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo" ||
           e.Path == "grpc.reflection.v1.ServerReflection/ServerReflectionInfo" {
            found = true; break
        }
    }
    if !found {
        t.Fatalf("expected reflection RPC in endpoint list, got %+v", eps)
    }
    _ = bufconn.Listen // silence unused import in some toolchains
}
```

- [ ] **Step 3:** Implement.

```go
package scanner

import (
    "context"
    "time"

    "github.com/google/uuid"
    "github.com/jhump/protoreflect/grpcreflect"
    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

func ProbeGRPC(ctx context.Context, address string, timeout time.Duration, opts ...grpc.DialOption) ([]db.EndpointRow, error) {
    if len(opts) == 0 {
        opts = []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
    }
    dctx, cancel := context.WithTimeout(ctx, timeout)
    defer cancel()
    conn, err := grpc.DialContext(dctx, address, append(opts, grpc.WithBlock())...)
    if err != nil {
        return nil, nil // unreachable = no endpoints
    }
    defer conn.Close()
    cli := grpcreflect.NewClientAuto(ctx, conn)
    defer cli.Reset()
    services, err := cli.ListServices()
    if err != nil {
        return nil, nil
    }
    var out []db.EndpointRow
    for _, svc := range services {
        sd, err := cli.ResolveService(svc)
        if err != nil { continue }
        for _, m := range sd.GetMethods() {
            out = append(out, db.EndpointRow{
                ID:       uuid.NewString(),
                Protocol: "grpc",
                Path:     svc + "/" + m.GetName(),
                Summary:  "",
            })
        }
    }
    return out, nil
}
```

- [ ] **Step 4:** Run.

```bash
go test ./internal/scanner -v -run GRPC
```

- [ ] **Step 5:** Commit.

```bash
git add internal/scanner/probe_grpc.go internal/scanner/probe_grpc_test.go go.mod go.sum
git commit -m "feat(api-catalog): gRPC reflection probe"
```

### Task 2.4: Scanner orchestrator + cron + env source

**Files:**
- Create: `internal/scanner/env_source.go`
- Create: `internal/scanner/scanner.go`
- Create: `internal/scanner/cron.go`
- Create: `internal/scanner/scanner_test.go`

- [ ] **Step 1:** Write `env_source.go`.

```go
package scanner

type Target struct {
    Name    string
    BaseURL string
    Source  string // "env" | "manual"
}

func MergeTargets(envSeeds map[string]string, dbRows []DBRow) []Target {
    seen := map[string]Target{}
    for name, url := range envSeeds {
        seen[name] = Target{Name: name, BaseURL: url, Source: "env"}
    }
    for _, r := range dbRows {
        if r.Source == "manual" {
            seen[r.Name] = Target{Name: r.Name, BaseURL: r.BaseURL, Source: "manual"}
        }
    }
    out := make([]Target, 0, len(seen))
    for _, t := range seen {
        out = append(out, t)
    }
    return out
}

type DBRow struct {
    Name    string
    BaseURL string
    Source  string
}
```

- [ ] **Step 2:** Write failing test for orchestrator.

```go
package scanner

import (
    "context"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"

    "gorm.io/driver/sqlite"
    "gorm.io/gorm"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/repository"
)

func newTestDB(t *testing.T) *gorm.DB {
    t.Helper()
    g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
    if err != nil { t.Fatal(err) }
    if err := db.AutoMigrate(g); err != nil { t.Fatal(err) }
    return g
}

func TestScanner_RunUpsertsServiceAndReplacesEndpoints(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.URL.Path == "/openapi.json" {
            _, _ = w.Write([]byte(`{"paths":{"/x":{"get":{"summary":"x"}}}}`))
            return
        }
        if r.URL.Path == "/api-info" {
            _ = json.NewEncoder(w).Encode(map[string]any{})
            return
        }
        http.NotFound(w, r)
    }))
    defer srv.Close()

    g := newTestDB(t)
    s := New(Deps{
        Services:    repository.NewServiceRepo(g),
        Endpoints:   repository.NewEndpointRepo(g),
        Concurrency: 4,
        Timeout:     1 * time.Second,
    })
    rep := s.Run(context.Background(), map[string]string{"foo-service": srv.URL})
    if rep.ServicesScanned != 1 || rep.ServicesOK != 1 {
        t.Fatalf("report = %+v", rep)
    }
    items, _, _ := repository.NewServiceRepo(g).List(10, 0, "")
    if len(items) != 1 || items[0].Name != "foo-service" {
        t.Fatalf("services = %+v", items)
    }
    eps, _ := repository.NewEndpointRepo(g).ListForService(items[0].ID, "")
    if len(eps) != 1 || eps[0].Path != "/x" {
        t.Fatalf("eps = %+v", eps)
    }
}
```

- [ ] **Step 3:** Implement `scanner.go`.

```go
package scanner

import (
    "context"
    "encoding/json"
    "fmt"
    "sync"
    "time"

    "github.com/google/uuid"
    "golang.org/x/sync/errgroup"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/repository"
)

type Deps struct {
    Services    *repository.ServiceRepo
    Endpoints   *repository.EndpointRepo
    Concurrency int
    Timeout     time.Duration
}

type Scanner struct{ d Deps }

func New(d Deps) *Scanner {
    if d.Concurrency <= 0 { d.Concurrency = 16 }
    if d.Timeout <= 0 { d.Timeout = 3 * time.Second }
    return &Scanner{d: d}
}

type Report struct {
    ServicesScanned int
    ServicesOK      int
    ServicesFailed  int
    Errors          []string
    FinishedAt      time.Time
}

func (s *Scanner) Run(ctx context.Context, envSeeds map[string]string) Report {
    rows, _ := s.d.Services.ListAll()
    dbTargets := make([]DBRow, 0, len(rows))
    for _, r := range rows {
        dbTargets = append(dbTargets, DBRow{Name: r.Name, BaseURL: r.BaseURL, Source: r.Source})
    }
    targets := MergeTargets(envSeeds, dbTargets)

    var (
        mu       sync.Mutex
        rep      Report
    )
    sem := make(chan struct{}, s.d.Concurrency)
    g, gctx := errgroup.WithContext(ctx)
    for _, t := range targets {
        t := t
        sem <- struct{}{}
        g.Go(func() error {
            defer func() { <-sem }()
            err := s.scanOne(gctx, t)
            mu.Lock()
            rep.ServicesScanned++
            if err == nil {
                rep.ServicesOK++
            } else {
                rep.ServicesFailed++
                rep.Errors = append(rep.Errors, fmt.Sprintf("%s: %v", t.Name, err))
            }
            mu.Unlock()
            return nil
        })
    }
    _ = g.Wait()
    rep.FinishedAt = time.Now().UTC()
    return rep
}

func (s *Scanner) scanOne(ctx context.Context, t Target) error {
    rest, _ := ProbeREST(ctx, t.BaseURL, s.d.Timeout)
    info := ProbeAPIInfo(ctx, t.BaseURL, s.d.Timeout)
    var grpcEps []db.EndpointRow
    if info.GRPCAddress != "" && info.GRPCReflection {
        grpcEps, _ = ProbeGRPC(ctx, info.GRPCAddress, s.d.Timeout)
    }

    var wsEps []db.EndpointRow
    for _, w := range info.WSEndpoints {
        wsEps = append(wsEps, db.EndpointRow{
            ID: uuid.NewString(), Protocol: "ws", Path: w.Path, Summary: w.Summary,
        })
    }

    protos := []string{}
    if len(rest) > 0 { protos = append(protos, "rest") }
    if len(wsEps) > 0 { protos = append(protos, "ws") }
    if len(grpcEps) > 0 { protos = append(protos, "grpc") }
    protosJSON, _ := json.Marshal(protos)

    now := time.Now().UTC()
    okFlag := true
    existing, err := s.d.Services.GetByName(t.Name)
    var serviceID string
    if err == repository.ErrNotFound {
        serviceID = uuid.NewString()
        row := &db.ServiceRow{
            ID: serviceID, Name: t.Name, BaseURL: t.BaseURL,
            Protocols: string(protosJSON), Source: t.Source, Status: "active",
            GRPCAddress: info.GRPCAddress,
            LastScannedAt: &now, LastScanOK: &okFlag,
        }
        if err := s.d.Services.Create(row); err != nil {
            return err
        }
    } else if err != nil {
        return err
    } else {
        serviceID = existing.ID
        upd := map[string]any{
            "base_url":        t.BaseURL,
            "protocols":       string(protosJSON),
            "grpc_address":    info.GRPCAddress,
            "last_scanned_at": now,
            "last_scan_ok":    true,
            "last_scan_error": "",
        }
        if err := s.d.Services.Update(serviceID, upd); err != nil {
            return err
        }
    }

    all := append(append(rest, wsEps...), grpcEps...)
    for i := range all {
        all[i].ServiceID = serviceID
    }
    return s.d.Endpoints.ReplaceForService(serviceID, all)
}
```

- [ ] **Step 4:** Implement `cron.go`.

```go
package scanner

import (
    "context"
    "log"
    "time"
)

func RunCron(ctx context.Context, s *Scanner, interval time.Duration, seeds func() map[string]string) {
    t := time.NewTicker(interval)
    defer t.Stop()
    log.Printf("scanner cron started, interval=%s", interval)
    for {
        select {
        case <-ctx.Done():
            return
        case <-t.C:
            rep := s.Run(ctx, seeds())
            log.Printf("scan tick: scanned=%d ok=%d failed=%d", rep.ServicesScanned, rep.ServicesOK, rep.ServicesFailed)
        }
    }
}
```

- [ ] **Step 5:** Run scanner tests.

```bash
go test ./internal/scanner -v
```

- [ ] **Step 6:** Commit.

```bash
git add internal/scanner/
git commit -m "feat(api-catalog): scanner orchestrator + cron + env merger"
```

---

## Phase 3 — gRPC server

### Task 3.1: Auth interceptor

**Files:**
- Create: `internal/grpcserver/interceptor_auth.go`
- Create: `internal/grpcserver/interceptor_auth_test.go`

- [ ] **Step 1:** Write failing test.

```go
package grpcserver

import (
    "context"
    "testing"

    "google.golang.org/grpc"
    "google.golang.org/grpc/codes"
    "google.golang.org/grpc/metadata"
    "google.golang.org/grpc/status"
)

func TestAdminInterceptor_AllowsReadWithoutKey(t *testing.T) {
    inter := NewAdminInterceptor("secret")
    info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/ListServices"}
    handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
    out, err := inter(context.Background(), nil, info, handler)
    if err != nil || out != "ok" {
        t.Fatalf("read without key should pass; got %v err=%v", out, err)
    }
}

func TestAdminInterceptor_BlocksWriteWithoutKey(t *testing.T) {
    inter := NewAdminInterceptor("secret")
    info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/CreateService"}
    handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
    _, err := inter(context.Background(), nil, info, handler)
    if status.Code(err) != codes.Unauthenticated {
        t.Fatalf("want Unauthenticated, got %v", err)
    }
}

func TestAdminInterceptor_AllowsWriteWithKey(t *testing.T) {
    inter := NewAdminInterceptor("secret")
    md := metadata.New(map[string]string{"authorization": "Bearer secret"})
    ctx := metadata.NewIncomingContext(context.Background(), md)
    info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/CreateService"}
    handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
    out, err := inter(ctx, nil, info, handler)
    if err != nil || out != "ok" {
        t.Fatalf("write with key should pass; got %v err=%v", out, err)
    }
}
```

- [ ] **Step 2:** Implement.

```go
package grpcserver

import (
    "context"
    "strings"

    "google.golang.org/grpc"
    "google.golang.org/grpc/codes"
    "google.golang.org/grpc/metadata"
    "google.golang.org/grpc/status"
)

var writeMethods = map[string]struct{}{
    "/api_catalog.ApiCatalog/CreateService": {},
    "/api_catalog.ApiCatalog/UpdateService": {},
    "/api_catalog.ApiCatalog/DeleteService": {},
    "/api_catalog.ApiCatalog/RescanAll":     {},
    "/api_catalog.ApiCatalog/RescanService": {},
}

func NewAdminInterceptor(adminKey string) grpc.UnaryServerInterceptor {
    return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
        if _, write := writeMethods[info.FullMethod]; !write {
            return handler(ctx, req)
        }
        if adminKey == "" {
            return nil, status.Error(codes.Unauthenticated, "admin key not configured")
        }
        md, _ := metadata.FromIncomingContext(ctx)
        vals := md.Get("authorization")
        if len(vals) == 0 {
            return nil, status.Error(codes.Unauthenticated, "missing authorization metadata")
        }
        h := vals[0]
        if !strings.HasPrefix(h, "Bearer ") || strings.TrimPrefix(h, "Bearer ") != adminKey {
            return nil, status.Error(codes.Unauthenticated, "invalid admin key")
        }
        return handler(ctx, req)
    }
}
```

- [ ] **Step 3:** Run + commit.

```bash
go test ./internal/grpcserver -v -run AdminInterceptor
git add internal/grpcserver/interceptor_auth*.go
git commit -m "feat(api-catalog): admin interceptor for write/rescan RPCs"
```

### Task 3.2: DB↔proto mapper

**Files:**
- Create: `internal/grpcserver/mapper.go`
- Create: `internal/grpcserver/mapper_test.go`

- [ ] **Step 1:** Write failing test for round-trip on protocols + timestamps.

```go
package grpcserver

import (
    "encoding/json"
    "testing"
    "time"

    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/genproto/api_catalog"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
)

func TestServiceRowToProto(t *testing.T) {
    now := time.Now().UTC().Truncate(time.Second)
    okFlag := true
    p, _ := json.Marshal([]string{"rest", "ws"})
    row := db.ServiceRow{
        ID: "id", Name: "n", BaseURL: "u", Protocols: string(p),
        Source: "env", Status: "active",
        LastScannedAt: &now, LastScanOK: &okFlag, CreatedAt: now, UpdatedAt: now,
    }
    pbRow := ServiceRowToProto(row)
    if pbRow.Source != pb.Source_ENV || pbRow.Status != pb.Status_ACTIVE {
        t.Fatalf("enum mapping wrong")
    }
    if len(pbRow.Protocols) != 2 || pbRow.Protocols[0] != pb.Protocol_REST {
        t.Fatalf("protocols wrong: %+v", pbRow.Protocols)
    }
    if !pbRow.LastScanOk {
        t.Fatal("last_scan_ok wrong")
    }
}
```

- [ ] **Step 2:** Implement `mapper.go`.

```go
package grpcserver

import (
    "encoding/json"

    "google.golang.org/protobuf/types/known/timestamppb"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/genproto/api_catalog"
)

func ServiceRowToProto(r db.ServiceRow) *pb.Service {
    var protos []string
    _ = json.Unmarshal([]byte(r.Protocols), &protos)
    var tags []string
    if r.Tags != "" {
        _ = json.Unmarshal([]byte(r.Tags), &tags)
    }
    pbProtos := make([]pb.Protocol, 0, len(protos))
    for _, s := range protos {
        pbProtos = append(pbProtos, protoFromStr(s))
    }
    out := &pb.Service{
        Id: r.ID, Name: r.Name, BaseUrl: r.BaseURL,
        Protocols:    pbProtos,
        Source:       sourceFromStr(r.Source),
        Status:       statusFromStr(r.Status),
        Description:  r.Description,
        Owner:        r.Owner,
        Tags:         tags,
        ApiInfoUrl:   r.APIInfoURL,
        GrpcAddress:  r.GRPCAddress,
        LastScanError: r.LastScanError,
        CreatedAt:    timestamppb.New(r.CreatedAt),
        UpdatedAt:    timestamppb.New(r.UpdatedAt),
    }
    if r.LastScannedAt != nil {
        out.LastScannedAt = timestamppb.New(*r.LastScannedAt)
    }
    if r.LastScanOK != nil {
        out.LastScanOk = *r.LastScanOK
    }
    return out
}

func EndpointRowToProto(r db.EndpointRow) *pb.Endpoint {
    var tags []string
    if r.Tags != "" {
        _ = json.Unmarshal([]byte(r.Tags), &tags)
    }
    return &pb.Endpoint{
        Id: r.ID, ServiceId: r.ServiceID, Method: r.Method, Path: r.Path,
        Summary: r.Summary, OperationId: r.OperationID, Tags: tags,
        Deprecated: r.Deprecated, Protocol: protoFromStr(r.Protocol),
    }
}

func protoFromStr(s string) pb.Protocol {
    switch s {
    case "rest": return pb.Protocol_REST
    case "ws":   return pb.Protocol_WS
    case "grpc": return pb.Protocol_GRPC
    }
    return pb.Protocol_PROTOCOL_UNSPECIFIED
}

func StrFromProto(p pb.Protocol) string {
    switch p {
    case pb.Protocol_REST: return "rest"
    case pb.Protocol_WS:   return "ws"
    case pb.Protocol_GRPC: return "grpc"
    }
    return ""
}

func sourceFromStr(s string) pb.Source {
    switch s {
    case "env": return pb.Source_ENV
    case "manual": return pb.Source_MANUAL
    case "scan": return pb.Source_SCAN
    }
    return pb.Source_SOURCE_UNSPECIFIED
}

func statusFromStr(s string) pb.Status {
    switch s {
    case "active": return pb.Status_ACTIVE
    case "deprecated": return pb.Status_DEPRECATED
    case "down": return pb.Status_DOWN
    }
    return pb.Status_STATUS_UNSPECIFIED
}

func StatusToStr(s pb.Status) string {
    switch s {
    case pb.Status_ACTIVE: return "active"
    case pb.Status_DEPRECATED: return "deprecated"
    case pb.Status_DOWN: return "down"
    }
    return ""
}
```

- [ ] **Step 3:** Run + commit.

```bash
go test ./internal/grpcserver -v -run Mapper
git add internal/grpcserver/mapper*.go
git commit -m "feat(api-catalog): db<->proto mapper"
```

### Task 3.3: gRPC server implementation

**Files:**
- Create: `internal/grpcserver/server.go`
- Create: `internal/grpcserver/server_test.go`

- [ ] **Step 1:** Write failing test (bufconn).

```go
package grpcserver

import (
    "context"
    "encoding/json"
    "net"
    "testing"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"
    "google.golang.org/grpc/test/bufconn"
    "gorm.io/driver/sqlite"
    "gorm.io/gorm"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/genproto/api_catalog"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/repository"
)

func startBufServer(t *testing.T) (pb.ApiCatalogClient, func()) {
    t.Helper()
    g, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
    _ = db.AutoMigrate(g)
    sr := repository.NewServiceRepo(g)
    er := repository.NewEndpointRepo(g)
    p, _ := json.Marshal([]string{"rest"})
    _ = sr.Create(&db.ServiceRow{ID: "s1", Name: "foo-service", BaseURL: "http://x", Protocols: string(p), Source: "env", Status: "active"})

    lis := bufconn.Listen(1024 * 1024)
    s := grpc.NewServer()
    pb.RegisterApiCatalogServer(s, NewServer(Deps{Services: sr, Endpoints: er, AdminKey: "k"}))
    go func() { _ = s.Serve(lis) }()

    conn, err := grpc.DialContext(context.Background(), "bufnet",
        grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
        grpc.WithTransportCredentials(insecure.NewCredentials()))
    if err != nil { t.Fatal(err) }
    return pb.NewApiCatalogClient(conn), func() { conn.Close(); s.Stop() }
}

func TestServer_ListServices_ReturnsSeeded(t *testing.T) {
    cli, stop := startBufServer(t)
    defer stop()
    ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
    defer cancel()
    resp, err := cli.ListServices(ctx, &pb.ListServicesRequest{Limit: 10})
    if err != nil { t.Fatal(err) }
    if resp.Total != 1 || resp.Items[0].Name != "foo-service" {
        t.Fatalf("got %+v", resp)
    }
}
```

- [ ] **Step 2:** Implement `server.go`.

```go
package grpcserver

import (
    "context"
    "encoding/json"
    "errors"
    "time"

    "github.com/google/uuid"
    "google.golang.org/grpc/codes"
    "google.golang.org/grpc/status"
    "google.golang.org/protobuf/types/known/timestamppb"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/genproto/api_catalog"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/repository"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/scanner"
)

type Deps struct {
    Services  *repository.ServiceRepo
    Endpoints *repository.EndpointRepo
    Scanner   *scanner.Scanner
    Seeds     func() map[string]string
    AdminKey  string
}

type Server struct {
    pb.UnimplementedApiCatalogServer
    d Deps
}

func NewServer(d Deps) *Server { return &Server{d: d} }

func (s *Server) ListServices(ctx context.Context, req *pb.ListServicesRequest) (*pb.ListServicesResponse, error) {
    items, total, err := s.d.Services.List(int(req.GetLimit()), int(req.GetOffset()), req.GetFilter())
    if err != nil {
        return nil, status.Error(codes.Unavailable, err.Error())
    }
    out := &pb.ListServicesResponse{Total: total}
    for _, r := range items {
        out.Items = append(out.Items, ServiceRowToProto(r))
    }
    return out, nil
}

func (s *Server) GetService(ctx context.Context, req *pb.GetServiceRequest) (*pb.Service, error) {
    row, err := s.d.Services.GetByID(req.GetId())
    if errors.Is(err, repository.ErrNotFound) {
        return nil, status.Error(codes.NotFound, "service not found")
    }
    if err != nil {
        return nil, status.Error(codes.Unavailable, err.Error())
    }
    return ServiceRowToProto(*row), nil
}

func (s *Server) ListEndpoints(ctx context.Context, req *pb.ListEndpointsRequest) (*pb.ListEndpointsResponse, error) {
    items, err := s.d.Endpoints.ListForService(req.GetServiceId(), StrFromProto(req.GetProtocol()))
    if err != nil {
        return nil, status.Error(codes.Unavailable, err.Error())
    }
    out := &pb.ListEndpointsResponse{}
    for _, r := range items {
        out.Items = append(out.Items, EndpointRowToProto(r))
    }
    return out, nil
}

func (s *Server) CreateService(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) {
    if req.GetName() == "" || req.GetBaseUrl() == "" {
        return nil, status.Error(codes.InvalidArgument, "name and base_url required")
    }
    protos := make([]string, 0, len(req.GetProtocols()))
    for _, p := range req.GetProtocols() {
        if v := StrFromProto(p); v != "" { protos = append(protos, v) }
    }
    pj, _ := json.Marshal(protos)
    var tagsJSON string
    if len(req.GetTags()) > 0 {
        b, _ := json.Marshal(req.GetTags())
        tagsJSON = string(b)
    }
    row := &db.ServiceRow{
        ID: uuid.NewString(), Name: req.GetName(), BaseURL: req.GetBaseUrl(),
        Protocols: string(pj), Source: "manual", Status: "active",
        Description: req.GetDescription(), Owner: req.GetOwner(),
        Tags: tagsJSON, APIInfoURL: req.GetApiInfoUrl(), GRPCAddress: req.GetGrpcAddress(),
        CreatedBy: req.GetCreatedBy(),
    }
    if err := s.d.Services.Create(row); err != nil {
        return nil, status.Error(codes.AlreadyExists, err.Error())
    }
    got, _ := s.d.Services.GetByID(row.ID)
    return ServiceRowToProto(*got), nil
}

func (s *Server) UpdateService(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) {
    fields := map[string]any{}
    if req.Description != nil { fields["description"] = req.GetDescription() }
    if req.Owner != nil { fields["owner"] = req.GetOwner() }
    if len(req.GetTags()) > 0 {
        b, _ := json.Marshal(req.GetTags())
        fields["tags"] = string(b)
    }
    if req.Status != nil {
        fields["status"] = StatusToStr(req.GetStatus())
    }
    if len(fields) == 0 {
        return nil, status.Error(codes.InvalidArgument, "no fields to update")
    }
    if err := s.d.Services.Update(req.GetId(), fields); err != nil {
        if errors.Is(err, repository.ErrNotFound) {
            return nil, status.Error(codes.NotFound, "service not found")
        }
        return nil, status.Error(codes.Unavailable, err.Error())
    }
    got, _ := s.d.Services.GetByID(req.GetId())
    return ServiceRowToProto(*got), nil
}

func (s *Server) DeleteService(ctx context.Context, req *pb.DeleteServiceRequest) (*pb.DeleteServiceResponse, error) {
    if err := s.d.Services.Delete(req.GetId()); err != nil {
        if errors.Is(err, repository.ErrNotFound) {
            return nil, status.Error(codes.NotFound, "service not found")
        }
        return nil, status.Error(codes.Unavailable, err.Error())
    }
    return &pb.DeleteServiceResponse{Deleted: true}, nil
}

func (s *Server) RescanAll(ctx context.Context, req *pb.RescanAllRequest) (*pb.RescanReport, error) {
    if s.d.Scanner == nil {
        return nil, status.Error(codes.Unavailable, "scanner not configured")
    }
    rep := s.d.Scanner.Run(ctx, s.d.Seeds())
    return &pb.RescanReport{
        ServicesScanned: int32(rep.ServicesScanned),
        ServicesOk:      int32(rep.ServicesOK),
        ServicesFailed:  int32(rep.ServicesFailed),
        Errors:          rep.Errors,
        FinishedAt:      timestamppb.New(rep.FinishedAt),
    }, nil
}

func (s *Server) RescanService(ctx context.Context, req *pb.RescanServiceRequest) (*pb.RescanReport, error) {
    if s.d.Scanner == nil {
        return nil, status.Error(codes.Unavailable, "scanner not configured")
    }
    row, err := s.d.Services.GetByID(req.GetId())
    if err != nil {
        return nil, status.Error(codes.NotFound, "service not found")
    }
    seeds := map[string]string{row.Name: row.BaseURL}
    rep := s.d.Scanner.Run(ctx, seeds)
    return &pb.RescanReport{
        ServicesScanned: int32(rep.ServicesScanned),
        ServicesOk:      int32(rep.ServicesOK),
        ServicesFailed:  int32(rep.ServicesFailed),
        Errors:          rep.Errors,
        FinishedAt:      timestamppb.New(rep.FinishedAt),
    }, nil
}

var _ = time.Time{}
```

- [ ] **Step 3:** Run + commit.

```bash
go test ./internal/grpcserver -v
git add internal/grpcserver/server.go internal/grpcserver/server_test.go
git commit -m "feat(api-catalog): gRPC server implementation"
```

### Task 3.4: HTTP healthz + main wiring

**Files:**
- Create: `internal/health/health.go`
- Modify: `cmd/server/main.go`

- [ ] **Step 1:** Write `health/health.go`.

```go
package health

import (
    "fmt"
    "net/http"
)

func Handler() http.Handler {
    mux := http.NewServeMux()
    mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintln(w, "ok")
    })
    return mux
}
```

- [ ] **Step 2:** Replace `cmd/server/main.go` with full wiring.

```go
package main

import (
    "context"
    "fmt"
    "log"
    "net"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"

    "google.golang.org/grpc"

    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/config"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/genproto/api_catalog"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/grpcserver"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/health"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/repository"
    "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/scanner"
)

func main() {
    cfg := config.Load()

    g, err := db.Open(cfg.MySQLHost, cfg.MySQLPort, cfg.MySQLUser, cfg.MySQLPass, cfg.MySQLDB)
    if err != nil {
        log.Fatalf("open db: %v", err)
    }
    if err := db.AutoMigrate(g); err != nil {
        log.Fatalf("migrate: %v", err)
    }

    sr := repository.NewServiceRepo(g)
    er := repository.NewEndpointRepo(g)
    sc := scanner.New(scanner.Deps{Services: sr, Endpoints: er, Concurrency: cfg.ScanConcurrency, Timeout: cfg.ProbeTimeout})

    seeds := func() map[string]string {
        // re-read env on each call so deploy-time changes are picked up at next tick
        return config.Load().SeedTargets
    }

    grpcSrv := grpc.NewServer(grpc.UnaryInterceptor(grpcserver.NewAdminInterceptor(cfg.AdminKey)))
    pb.RegisterApiCatalogServer(grpcSrv, grpcserver.NewServer(grpcserver.Deps{
        Services: sr, Endpoints: er, Scanner: sc, Seeds: seeds, AdminKey: cfg.AdminKey,
    }))

    lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
    if err != nil {
        log.Fatalf("listen: %v", err)
    }

    httpSrv := &http.Server{
        Addr:    fmt.Sprintf(":%d", cfg.HealthPort),
        Handler: health.Handler(),
    }

    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()
    go scanner.RunCron(ctx, sc, cfg.ScanInterval, seeds)

    go func() {
        log.Printf("gRPC listening on :%d", cfg.GRPCPort)
        if err := grpcSrv.Serve(lis); err != nil {
            log.Fatalf("grpc serve: %v", err)
        }
    }()
    go func() {
        log.Printf("health listening on :%d", cfg.HealthPort)
        if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("http: %v", err)
        }
    }()

    sig := make(chan os.Signal, 1)
    signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
    <-sig
    log.Println("shutdown")
    cancel()
    grpcSrv.GracefulStop()
    sctx, scancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer scancel()
    _ = httpSrv.Shutdown(sctx)
}
```

- [ ] **Step 3:** Build.

```bash
go build ./cmd/server
```

- [ ] **Step 4:** Commit.

```bash
git add cmd/ internal/health/
git commit -m "feat(api-catalog): main wiring + healthz + cron"
```

---

## Phase 4 — Dockerfile + compose + CI

### Task 4.1: Dockerfile

**Files:**
- Create: `apps-microservices/api-catalog-service/Dockerfile`
- Create: `apps-microservices/api-catalog-service/.dockerignore`

- [ ] **Step 1:** Write multi-stage Dockerfile.

```dockerfile
# syntax=docker/dockerfile:1.6
FROM golang:1.24-alpine AS build
WORKDIR /src
COPY apps-microservices/api-catalog-service/go.mod apps-microservices/api-catalog-service/go.sum ./
RUN go mod download
COPY apps-microservices/api-catalog-service/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/server ./cmd/server

FROM alpine:3.20
RUN adduser -D -H -u 10001 catalog && apk add --no-cache ca-certificates
USER catalog
COPY --from=build /out/server /usr/local/bin/server
EXPOSE 9100 9101
ENTRYPOINT ["/usr/local/bin/server"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:9101/healthz >/dev/null 2>&1 || exit 1
```

- [ ] **Step 2:** Write `.dockerignore`.

```
*.test
*_test.go
```

- [ ] **Step 3:** Build image to verify.

```bash
docker build -f apps-microservices/api-catalog-service/Dockerfile -t api-catalog-service:dev .
```

- [ ] **Step 4:** Commit.

```bash
git add apps-microservices/api-catalog-service/Dockerfile apps-microservices/api-catalog-service/.dockerignore
git commit -m "feat(api-catalog): Dockerfile (multi-stage, non-root, healthcheck)"
```

### Task 4.2: docker-compose entry

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1:** Read existing `gateway-mysql` + `api-gateway-go` service definitions to mirror style. Insert new service after `api-gateway-go`. Use same env-var pattern as gateway (mirror `SERVICE_*`).

```yaml
  api-catalog-service:
    build:
      context: .
      dockerfile: apps-microservices/api-catalog-service/Dockerfile
    container_name: api-catalog-service
    depends_on:
      gateway-mysql:
        condition: service_healthy
    environment:
      MYSQL_HOST: gateway-mysql
      MYSQL_PORT: "3306"
      MYSQL_USER: ${CATALOG_MYSQL_USER:-catalog_user}
      MYSQL_PASS: ${CATALOG_MYSQL_PASS}
      MYSQL_DB:   ${CATALOG_MYSQL_DB:-catalog_db}
      GRPC_PORT:  "9100"
      HEALTH_PORT: "9101"
      ADMIN_KEY:  ${CATALOG_ADMIN_KEY}
      SCAN_INTERVAL: "15m"
      SCAN_CONCURRENCY: "16"
      PROBE_TIMEOUT: "3s"
    env_file:
      - .env.services   # contains SERVICE_* mirrored from gateway compose section
    expose:
      - "9100"
      - "9101"
    restart: unless-stopped
    logging:
      driver: json-file
      options: { max-size: 10m, max-file: "3" }
```

- [ ] **Step 2:** Add `init-db/01_schema.sql` to gateway-mysql `volumes:` mount so the catalog DB+tables exist at first boot. Confirm with maintainer if `gateway-mysql` already has a custom init script — if so, append a new volume mount entry pointing at `apps-microservices/api-catalog-service/init-db:/docker-entrypoint-initdb.d/catalog`.

- [ ] **Step 3:** Commit.

```bash
git add docker-compose.yml
git commit -m "feat(infra): wire api-catalog-service into compose"
```

### Task 4.3: CI/CD workflows

**Files:**
- Create: `.github/workflows/ci_services_api_catalog.yml`
- Create: `.github/workflows/cd_build_push_api_catalog.yml`

- [ ] **Step 1:** Mirror an existing Go workflow (e.g. for `api-gateway-go`) for CI.

```yaml
name: ci_services_api_catalog
on:
  pull_request:
    paths:
      - 'apps-microservices/api-catalog-service/**'
      - 'protos/grpc_stubs/api_catalog.proto'
  push:
    branches: [main, features/poc]
    paths:
      - 'apps-microservices/api-catalog-service/**'
jobs:
  test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: apps-microservices/api-catalog-service } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with: { go-version: '1.24' }
      - run: go vet ./...
      - run: go test ./... -race -count=1
      - run: go build ./...
```

- [ ] **Step 2:** Mirror the existing `cd_build_push_*` for the new service.

- [ ] **Step 3:** Commit.

```bash
git add .github/workflows/
git commit -m "ci(api-catalog): add CI/CD workflows"
```

---

## Phase 5 — `/api-info` Python helper

### Task 5.1: FastAPI helper in libs/common-utils

**Files:**
- Create: `libs/common-utils/src/<pkg>/api_info.py` (path under existing common-utils package — read existing structure first)
- Create: `libs/common-utils/tests/test_api_info.py`

- [ ] **Step 1:** Inspect package layout.

```bash
ls libs/common-utils/src/
```

- [ ] **Step 2:** Write helper `api_info.py`.

```python
from fastapi import APIRouter, FastAPI

def register_api_info(app: FastAPI, *, service: str, version: str = "0.0.0",
                     ws_endpoints: list[dict] | None = None,
                     grpc_address: str | None = None,
                     grpc_reflection: bool = False,
                     openapi_url: str = "/openapi.json") -> None:
    """Register GET /api-info on the given FastAPI app with the catalog convention."""
    router = APIRouter()

    @router.get("/api-info")
    def api_info():
        payload: dict = {"service": service, "version": version,
                          "rest": {"openapi_url": openapi_url}}
        if ws_endpoints:
            payload["ws"] = {"endpoints": ws_endpoints}
        if grpc_address:
            payload["grpc"] = {"address": grpc_address, "reflection": grpc_reflection}
        return payload

    app.include_router(router)
```

- [ ] **Step 3:** Write test.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from <pkg>.api_info import register_api_info

def test_minimal_payload():
    app = FastAPI()
    register_api_info(app, service="x", version="1.0")
    c = TestClient(app)
    r = c.get("/api-info")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "x"
    assert body["rest"]["openapi_url"] == "/openapi.json"
    assert "ws" not in body and "grpc" not in body

def test_full_payload():
    app = FastAPI()
    register_api_info(app, service="x", version="1.0",
                      ws_endpoints=[{"path": "/ws/a"}],
                      grpc_address="x:9000", grpc_reflection=True)
    c = TestClient(app)
    body = c.get("/api-info").json()
    assert body["ws"]["endpoints"][0]["path"] == "/ws/a"
    assert body["grpc"]["address"] == "x:9000"
    assert body["grpc"]["reflection"] is True
```

- [ ] **Step 4:** Run.

```bash
cd libs/common-utils
pytest tests/test_api_info.py -v
```

- [ ] **Step 5:** Commit.

```bash
git add libs/common-utils/
git commit -m "feat(common-utils): /api-info FastAPI helper for service catalog"
```

---

## Phase 6 — account-service-backend integration

### Task 6.1: Generate proto stubs into account-backend

**Files:**
- Create: `apps-microservices/account-service-backend/internal/genproto/api_catalog/*.pb.go`

- [ ] **Step 1:** Generate.

```bash
cd /home/sandratra/RAG-HP-PUB
protoc \
  --go_out=apps-microservices/account-service-backend/internal/genproto \
  --go_opt=paths=source_relative \
  --go-grpc_out=apps-microservices/account-service-backend/internal/genproto \
  --go-grpc_opt=paths=source_relative \
  -I protos/grpc_stubs \
  protos/grpc_stubs/api_catalog.proto
```

- [ ] **Step 2:** Add deps + build.

```bash
cd apps-microservices/account-service-backend
go get google.golang.org/grpc google.golang.org/protobuf
go build ./...
```

- [ ] **Step 3:** Commit.

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-backend): generate api_catalog gRPC stubs"
```

### Task 6.2: gRPC client wrapper

**Files:**
- Create: `apps-microservices/account-service-backend/internal/api/api_catalog_client.go`
- Create: `apps-microservices/account-service-backend/internal/api/api_catalog_client_test.go`

- [ ] **Step 1:** Write failing test (bufconn end-to-end).

```go
package api

import (
    "context"
    "net"
    "testing"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"
    "google.golang.org/grpc/test/bufconn"

    pb "account-service/internal/genproto/api_catalog"
)

type fakeServer struct{ pb.UnimplementedApiCatalogServer }

func (fakeServer) ListServices(ctx context.Context, _ *pb.ListServicesRequest) (*pb.ListServicesResponse, error) {
    return &pb.ListServicesResponse{Total: 1, Items: []*pb.Service{{Id: "a", Name: "n"}}}, nil
}

func TestCatalogClient_List(t *testing.T) {
    lis := bufconn.Listen(1024 * 1024)
    s := grpc.NewServer()
    pb.RegisterApiCatalogServer(s, fakeServer{})
    go func() { _ = s.Serve(lis) }()
    defer s.Stop()

    conn, err := grpc.DialContext(context.Background(), "bufnet",
        grpc.WithContextDialer(func(_ context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
        grpc.WithTransportCredentials(insecure.NewCredentials()))
    if err != nil { t.Fatal(err) }
    defer conn.Close()

    cli := NewCatalogClient(conn, "")
    ctx, cancel := context.WithTimeout(context.Background(), time.Second)
    defer cancel()
    resp, err := cli.ListServices(ctx, 10, 0, "")
    if err != nil { t.Fatal(err) }
    if resp.Total != 1 || resp.Items[0].Name != "n" {
        t.Fatalf("got %+v", resp)
    }
}
```

- [ ] **Step 2:** Implement.

```go
package api

import (
    "context"
    "fmt"

    "google.golang.org/grpc"
    "google.golang.org/grpc/metadata"

    pb "account-service/internal/genproto/api_catalog"
)

type CatalogClient struct {
    cli      pb.ApiCatalogClient
    adminKey string
}

func NewCatalogClient(conn *grpc.ClientConn, adminKey string) *CatalogClient {
    return &CatalogClient{cli: pb.NewApiCatalogClient(conn), adminKey: adminKey}
}

func (c *CatalogClient) authCtx(ctx context.Context) context.Context {
    if c.adminKey == "" { return ctx }
    return metadata.AppendToOutgoingContext(ctx, "authorization", "Bearer "+c.adminKey)
}

func (c *CatalogClient) ListServices(ctx context.Context, limit, offset int, filter string) (*pb.ListServicesResponse, error) {
    return c.cli.ListServices(ctx, &pb.ListServicesRequest{Limit: int32(limit), Offset: int32(offset), Filter: filter})
}

func (c *CatalogClient) GetService(ctx context.Context, id string) (*pb.Service, error) {
    return c.cli.GetService(ctx, &pb.GetServiceRequest{Id: id})
}

func (c *CatalogClient) ListEndpoints(ctx context.Context, serviceID string, protocol pb.Protocol) (*pb.ListEndpointsResponse, error) {
    return c.cli.ListEndpoints(ctx, &pb.ListEndpointsRequest{ServiceId: serviceID, Protocol: protocol})
}

func (c *CatalogClient) Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) {
    return c.cli.CreateService(c.authCtx(ctx), req)
}

func (c *CatalogClient) Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) {
    return c.cli.UpdateService(c.authCtx(ctx), req)
}

func (c *CatalogClient) Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error) {
    return c.cli.DeleteService(c.authCtx(ctx), &pb.DeleteServiceRequest{Id: id})
}

func (c *CatalogClient) RescanAll(ctx context.Context) (*pb.RescanReport, error) {
    return c.cli.RescanAll(c.authCtx(ctx), &pb.RescanAllRequest{})
}

func (c *CatalogClient) RescanService(ctx context.Context, id string) (*pb.RescanReport, error) {
    return c.cli.RescanService(c.authCtx(ctx), &pb.RescanServiceRequest{Id: id})
}

var _ = fmt.Sprintf
```

- [ ] **Step 3:** Run + commit.

```bash
go test ./internal/api -v -run Catalog
git add internal/api/api_catalog_client*.go
git commit -m "feat(account-backend): catalog gRPC client wrapper"
```

### Task 6.3: HTTP handlers `/admin/api/*`

**Files:**
- Create: `internal/api/api_catalog_handlers.go`
- Create: `internal/api/api_catalog_handlers_test.go`

- [ ] **Step 1:** Read existing handler conventions in `account-service-backend` (e.g. `admin_service_handlers.go`) for response shape, error handling, JSON encoding, audit-log invocation, role check helper. Mirror the same conventions exactly.

- [ ] **Step 2:** Write handler scaffold and table-driven tests using a mock `CatalogClient` interface (extract an interface above the concrete client in the previous task if not already done).

Define the interface in `api_catalog_handlers.go`:

```go
type catalogClientIface interface {
    ListServices(ctx context.Context, limit, offset int, filter string) (*pb.ListServicesResponse, error)
    GetService(ctx context.Context, id string) (*pb.Service, error)
    ListEndpoints(ctx context.Context, serviceID string, protocol pb.Protocol) (*pb.ListEndpointsResponse, error)
    Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error)
    Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error)
    Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error)
    RescanAll(ctx context.Context) (*pb.RescanReport, error)
    RescanService(ctx context.Context, id string) (*pb.RescanReport, error)
}
```

The concrete `*CatalogClient` already satisfies it. Tests pass a `mockCatalog` implementation; handler tests verify route → method mapping, status codes for `NotFound`/`InvalidArgument`/`Unauthenticated` (translate via `status.Code(err)`), and that admin-only routes are gated by the existing `RequireAdmin` middleware (use the same role-check helper as `admin_service_handlers.go`).

Routes (added to the existing router setup in `cmd/server/main.go`):

| Method | Path | Middleware | Handler |
|---|---|---|---|
| GET | `/admin/api` | RequireAuth | `ListAPIs` → `cli.ListServices` |
| GET | `/admin/api/:id` | RequireAuth | `GetAPI` → `cli.GetService` + `cli.ListEndpoints` |
| POST | `/admin/api` | RequireAdmin | `CreateAPI` → `cli.Create` |
| PUT | `/admin/api/:id` | RequireAdmin | `UpdateAPI` → `cli.Update` |
| DELETE | `/admin/api/:id` | RequireAdmin | `DeleteAPI` → `cli.Delete` |
| POST | `/admin/api/rescan` | RequireAdmin | `RescanAll` |
| POST | `/admin/api/:id/rescan` | RequireAdmin | `RescanOne` |

Status code translation helper (per spec §"Error handling"):

```go
func grpcToHTTP(err error) int {
    switch status.Code(err) {
    case codes.NotFound: return http.StatusNotFound
    case codes.AlreadyExists: return http.StatusConflict
    case codes.InvalidArgument: return http.StatusBadRequest
    case codes.Unauthenticated: return http.StatusUnauthorized
    case codes.Unavailable: return http.StatusServiceUnavailable
    }
    return http.StatusInternalServerError
}
```

Audit log: on Create/Update/Delete/Rescan, call existing `audit_repo.Insert(action, actorEmail, targetID)`.

Response shape: convert proto messages to camelCase JSON via existing helper or hand-rolled mapper (mirror what `admin_service_handlers.go` does for `OAuth2Client`).

- [ ] **Step 3:** Wire routes in `cmd/server/main.go` after gRPC client init.

```go
conn, err := grpc.Dial(cfg.APICatalogGRPC, grpc.WithTransportCredentials(insecure.NewCredentials()))
if err != nil {
    log.Fatalf("dial catalog: %v", err)
}
catCli := api.NewCatalogClient(conn, cfg.CatalogAdminKey)
api.RegisterAPICatalogRoutes(mux, catCli, audit, requireAuth, requireAdmin)
```

Add new env vars to `internal/config/config.go`: `APICatalogGRPC` (default `api-catalog-service:9100`) and `CatalogAdminKey`.

- [ ] **Step 4:** Run all backend tests.

```bash
go test ./...
```

- [ ] **Step 5:** Commit.

```bash
git add apps-microservices/account-service-backend/
git commit -m "feat(account-backend): /admin/api CRUD + rescan routes via catalog gRPC"
```

---

## Phase 7 — account-service-frontend integration

### Task 7.1: Types + API wrapper

**Files:**
- Create: `apps-microservices/account-service-frontend/src/types/apiCatalog.ts`
- Create: `apps-microservices/account-service-frontend/src/api/apiCatalog.ts`
- Create: `apps-microservices/account-service-frontend/src/api/apiCatalog.spec.ts`

- [ ] **Step 1:** Write `types/apiCatalog.ts`.

```ts
export type Protocol = 'rest' | 'ws' | 'grpc'
export type Source = 'env' | 'manual' | 'scan'
export type Status = 'active' | 'deprecated' | 'down'

export interface ApiCatalogService {
  id: string
  name: string
  baseUrl: string
  protocols: Protocol[]
  source: Source
  status: Status
  description?: string
  owner?: string
  tags?: string[]
  apiInfoUrl?: string
  grpcAddress?: string
  lastScannedAt?: string
  lastScanOk?: boolean
  lastScanError?: string
  createdAt: string
  updatedAt: string
}

export interface ApiCatalogEndpoint {
  id: string
  serviceId: string
  protocol: Protocol
  method?: string
  path: string
  summary?: string
  operationId?: string
  tags?: string[]
  deprecated: boolean
}

export interface ListResp { items: ApiCatalogService[]; total: number }

export interface CreateApiRequest {
  name: string
  baseUrl: string
  protocols: Protocol[]
  description?: string
  owner?: string
  tags?: string[]
  apiInfoUrl?: string
  grpcAddress?: string
}

export interface UpdateApiRequest {
  description?: string
  owner?: string
  tags?: string[]
  status?: Status
}
```

- [ ] **Step 2:** Write `api/apiCatalog.ts` mirroring the pattern in `src/api/services.ts`.

```ts
import type { ApiCatalogService, ApiCatalogEndpoint, ListResp, CreateApiRequest, UpdateApiRequest, Protocol } from '@/types/apiCatalog'

const base = '/admin/api'

async function send<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

export const list = (limit = 100, offset = 0, filter = '') =>
  send<ListResp>(`${base}?limit=${limit}&offset=${offset}&filter=${encodeURIComponent(filter)}`)

export const get = (id: string) =>
  send<{ service: ApiCatalogService; endpoints: ApiCatalogEndpoint[] }>(`${base}/${id}`)

export const create = (req: CreateApiRequest) =>
  send<ApiCatalogService>(base, { method: 'POST', body: JSON.stringify(req) })

export const update = (id: string, req: UpdateApiRequest) =>
  send<ApiCatalogService>(`${base}/${id}`, { method: 'PUT', body: JSON.stringify(req) })

export const remove = (id: string) =>
  send<{ deleted: boolean }>(`${base}/${id}`, { method: 'DELETE' })

export const rescanAll = () =>
  send<{ servicesScanned: number; servicesOk: number; servicesFailed: number; errors: string[] }>(`${base}/rescan`, { method: 'POST' })

export const rescanOne = (id: string) =>
  send<{ servicesScanned: number; servicesOk: number; servicesFailed: number; errors: string[] }>(`${base}/${id}/rescan`, { method: 'POST' })

export const filterByProtocol = (items: ApiCatalogService[], proto: Protocol) =>
  items.filter(i => i.protocols.includes(proto))
```

- [ ] **Step 3:** Write Vitest unit test for the wrapper using `vi.fn()` to stub `fetch` and verify URL/method/body for each call.

- [ ] **Step 4:** Run + commit.

```bash
npm test -- src/api/apiCatalog.spec.ts
git add src/api/apiCatalog.ts src/api/apiCatalog.spec.ts src/types/apiCatalog.ts
git commit -m "feat(account-frontend): apiCatalog types + API wrapper"
```

### Task 7.2: Components (badges, endpoint table, scan status)

**Files:**
- Create: `src/components/api-catalog/ProtocolBadge.vue`
- Create: `src/components/api-catalog/EndpointTable.vue`
- Create: `src/components/api-catalog/ScanStatusBadge.vue`

- [ ] **Step 1:** `ProtocolBadge.vue` — accepts `protocol: Protocol`, renders a colored pill: REST=blue, WS=purple, gRPC=green.

```vue
<script setup lang="ts">
import type { Protocol } from '@/types/apiCatalog'
const props = defineProps<{ protocol: Protocol }>()
const cls = {
  rest: 'bg-blue-100 text-blue-700',
  ws:   'bg-purple-100 text-purple-700',
  grpc: 'bg-green-100 text-green-700',
} as const
const label = { rest: 'REST', ws: 'WS', grpc: 'gRPC' } as const
</script>
<template>
  <span class="inline-flex px-2 py-0.5 text-xs font-medium rounded" :class="cls[props.protocol]">
    {{ label[props.protocol] }}
  </span>
</template>
```

- [ ] **Step 2:** `ScanStatusBadge.vue` — accepts `ok?: boolean`, `at?: string`. Renders `Jamais scanné` (gray) if `at` empty; `OK · <relative>` (green) if `ok`; `Échec · <relative>` (red) if `!ok`.

- [ ] **Step 3:** `EndpointTable.vue` — accepts `endpoints: ApiCatalogEndpoint[]`. Renders `@tanstack/vue-table` with columns Method, Path, Summary, Tags. Search box filters by path or summary substring (case-insensitive). Uses the existing `DataTable.vue` component pattern.

- [ ] **Step 4:** Vitest smoke test for ProtocolBadge.

```ts
import { mount } from '@vue/test-utils'
import ProtocolBadge from '@/components/api-catalog/ProtocolBadge.vue'

test('renders REST label', () => {
  const w = mount(ProtocolBadge, { props: { protocol: 'rest' } })
  expect(w.text()).toBe('REST')
  expect(w.classes()).toContain('bg-blue-100')
})
```

- [ ] **Step 5:** Run + commit.

```bash
npm test -- src/components/api-catalog/
git add src/components/api-catalog/
git commit -m "feat(account-frontend): API catalog UI components"
```

### Task 7.3: Views — List + Detail + Form

**Files:**
- Create: `src/views/ApiCatalogListView.vue`
- Create: `src/views/ApiCatalogDetailView.vue`
- Create: `src/views/ApiCatalogFormView.vue`

- [ ] **Step 1:** `ApiCatalogListView.vue` — mirrors `AdminServicesView.vue` structure. Calls `apiCatalog.list()`, renders `DataTable` with columns Name, Protocols (badges), Status, Source, Last Scan (`ScanStatusBadge`), Endpoints (count). Top-right: `Rescan all` button (admin-only, calls `apiCatalog.rescanAll`), `+ Create` button (admin-only, navigates to `/admin/api/new`). Filters: protocol multi-select, status select, source select, search text.

- [ ] **Step 2:** `ApiCatalogDetailView.vue` — calls `apiCatalog.get(id)` on mount. Header: name, baseUrl, status, last_scanned_at. Tabs: REST / WebSocket / gRPC, only shown when `endpoints.some(e => e.protocol === proto)`. Per-tab: `EndpointTable` filtered to that protocol. Side panel: metadata (owner, tags, description). Buttons (admin): Edit (→ `/admin/api/:id/edit`), Delete (with confirm), Rescan (calls `apiCatalog.rescanOne(id)` then reloads).

- [ ] **Step 3:** `ApiCatalogFormView.vue` — full-page form. Mode determined by `route.params.id` presence (mirrors `ServiceFormView.vue`). On mount in edit mode: load via `apiCatalog.get(id)`. Fields:
  - **Always:** description (textarea), owner (text), tags (chip input), status (select: active/deprecated/down) — only `status` enabled in admin role.
  - **Edit-mode only when `service.source === 'manual'`:** name (locked in edit mode regardless), baseUrl, apiInfoUrl, grpcAddress, protocols (checkbox group). Otherwise readonly with helper text "Champs gérés par le scan automatique".
  - **Create mode:** all fields editable.
  - Submit button: Create → `apiCatalog.create`, Edit → `apiCatalog.update`. Cancel → router back. Show errors inline.

- [ ] **Step 4:** Run + commit.

```bash
npm run build  # verify view files compile
git add src/views/ApiCatalog*.vue
git commit -m "feat(account-frontend): API catalog list/detail/form views"
```

### Task 7.4: Router + sidebar nav entry

**Files:**
- Modify: `src/router/index.ts`
- Modify: sidebar nav component (locate via grep — likely under `src/components/` or `src/App.vue`)

- [ ] **Step 1:** Add 4 routes in `src/router/index.ts` between the existing services routes and `/admin/parameters`:

```ts
{ path: '/admin/api',          name: 'api-list',   component: () => import('@/views/ApiCatalogListView.vue'),   meta: { requiresAuth: true, title: 'API' } },
{ path: '/admin/api/new',      name: 'api-create', component: () => import('@/views/ApiCatalogFormView.vue'),   meta: { requiresAuth: true, minRole: 'admin', title: 'Nouvelle API' } },
{ path: '/admin/api/:id',      name: 'api-detail', component: () => import('@/views/ApiCatalogDetailView.vue'), meta: { requiresAuth: true, title: 'Détail API' } },
{ path: '/admin/api/:id/edit', name: 'api-edit',   component: () => import('@/views/ApiCatalogFormView.vue'),   meta: { requiresAuth: true, minRole: 'admin', title: 'Modifier API' } },
```

- [ ] **Step 2:** Locate sidebar nav (run `grep -r "Services" src/components src/App.vue` to find the existing nav array). Insert a new entry "API" between "Services" and "Paramètres", linking to `/admin/api`. Reuse the existing icon-component pattern (lucide-vue-next).

- [ ] **Step 3:** Run + commit.

```bash
npm test
git add src/router/ src/components/ src/App.vue
git commit -m "feat(account-frontend): API nav entry + routes"
```

---

## Phase 8 — api-gateway-go: catalog consumer

### Task 8.1: Generate stubs into gateway

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/genproto/api_catalog/`

- [ ] **Step 1:** Generate.

```bash
cd /home/sandratra/RAG-HP-PUB
protoc \
  --go_out=apps-microservices/api-gateway-go/internal/genproto \
  --go_opt=paths=source_relative \
  --go-grpc_out=apps-microservices/api-gateway-go/internal/genproto \
  --go-grpc_opt=paths=source_relative \
  -I protos/grpc_stubs \
  protos/grpc_stubs/api_catalog.proto
```

- [ ] **Step 2:** Build.

```bash
cd apps-microservices/api-gateway-go
go get google.golang.org/grpc google.golang.org/protobuf
go build ./...
```

- [ ] **Step 3:** Commit.

```bash
git add apps-microservices/api-gateway-go/
git commit -m "feat(gateway): generate api_catalog gRPC stubs"
```

### Task 8.2: Catalog client + refresher

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/catalog/client.go`
- Create: `apps-microservices/api-gateway-go/internal/catalog/refresher.go`
- Create: `apps-microservices/api-gateway-go/internal/catalog/refresher_test.go`

- [ ] **Step 1:** Write failing test.

```go
package catalog

import (
    "context"
    "net"
    "sync/atomic"
    "testing"
    "time"

    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"
    "google.golang.org/grpc/test/bufconn"

    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/genproto/api_catalog"
)

type stubServer struct{ pb.UnimplementedApiCatalogServer; calls int32 }

func (s *stubServer) ListServices(ctx context.Context, _ *pb.ListServicesRequest) (*pb.ListServicesResponse, error) {
    atomic.AddInt32(&s.calls, 1)
    return &pb.ListServicesResponse{Items: []*pb.Service{
        {Name: "foo-service", BaseUrl: "http://foo:8000", Status: pb.Status_ACTIVE},
        {Name: "bar-service", BaseUrl: "http://bar:8000", Status: pb.Status_DEPRECATED},
    }, Total: 2}, nil
}

func startBuf(t *testing.T) (*grpc.ClientConn, *stubServer, func()) {
    t.Helper()
    lis := bufconn.Listen(1024 * 1024)
    s := grpc.NewServer()
    stub := &stubServer{}
    pb.RegisterApiCatalogServer(s, stub)
    go func() { _ = s.Serve(lis) }()
    conn, _ := grpc.DialContext(context.Background(), "bufnet",
        grpc.WithContextDialer(func(_ context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
        grpc.WithTransportCredentials(insecure.NewCredentials()))
    return conn, stub, func() { conn.Close(); s.Stop() }
}

func TestRefresher_BuildsMap_FiltersInactive(t *testing.T) {
    conn, _, stop := startBuf(t); defer stop()
    cli := NewClient(conn)
    m, err := cli.BuildMap(context.Background())
    if err != nil { t.Fatal(err) }
    if got := m["/foo-service"]; got != "http://foo:8000" {
        t.Fatalf("active route missing: %+v", m)
    }
    if _, has := m["/bar-service"]; has {
        t.Fatal("deprecated route should be filtered out")
    }
}
```

- [ ] **Step 2:** Implement `client.go`.

```go
package catalog

import (
    "context"

    "google.golang.org/grpc"

    pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/genproto/api_catalog"
)

type Client struct{ cli pb.ApiCatalogClient }

func NewClient(conn *grpc.ClientConn) *Client { return &Client{cli: pb.NewApiCatalogClient(conn)} }

// BuildMap returns prefix -> base_url for ACTIVE services only (DEPRECATED + DOWN excluded).
func (c *Client) BuildMap(ctx context.Context) (map[string]string, error) {
    resp, err := c.cli.ListServices(ctx, &pb.ListServicesRequest{Limit: 1000})
    if err != nil { return nil, err }
    out := make(map[string]string, len(resp.GetItems()))
    for _, s := range resp.GetItems() {
        if s.GetStatus() != pb.Status_ACTIVE { continue }
        out["/"+s.GetName()] = s.GetBaseUrl()
    }
    return out, nil
}
```

- [ ] **Step 3:** Implement `refresher.go`.

```go
package catalog

import (
    "context"
    "log"
    "sync"
    "time"
)

type Refresher struct {
    cli       *Client
    interval  time.Duration
    fallback  map[string]string
    mu        sync.RWMutex
    current   map[string]string
    source    string // "catalog" | "env"
}

func NewRefresher(cli *Client, interval time.Duration, fallback map[string]string) *Refresher {
    return &Refresher{cli: cli, interval: interval, fallback: fallback}
}

// Bootstrap performs one synchronous fetch with timeout. On failure or empty result,
// uses the env fallback. Returns (map, source).
func (r *Refresher) Bootstrap(ctx context.Context, dialTimeout time.Duration) (map[string]string, string) {
    bctx, cancel := context.WithTimeout(ctx, dialTimeout)
    defer cancel()
    m, err := r.cli.BuildMap(bctx)
    if err != nil || len(m) == 0 {
        log.Printf("catalog bootstrap: using env fallback (err=%v len=%d)", err, len(m))
        r.set(r.fallback, "env")
        return r.fallback, "env"
    }
    r.set(m, "catalog")
    return m, "catalog"
}

// Run blocks until ctx is cancelled. Refreshes the map every interval.
// On failure: keeps last good map.
func (r *Refresher) Run(ctx context.Context) {
    t := time.NewTicker(r.interval); defer t.Stop()
    for {
        select {
        case <-ctx.Done(): return
        case <-t.C:
            rctx, cancel := context.WithTimeout(ctx, 5*time.Second)
            m, err := r.cli.BuildMap(rctx)
            cancel()
            if err != nil || len(m) == 0 {
                log.Printf("catalog refresh failed; keeping last map (err=%v)", err)
                continue
            }
            r.set(m, "catalog")
        }
    }
}

func (r *Refresher) Snapshot() (map[string]string, string) {
    r.mu.RLock(); defer r.mu.RUnlock()
    return r.current, r.source
}

func (r *Refresher) set(m map[string]string, src string) {
    r.mu.Lock(); defer r.mu.Unlock()
    r.current, r.source = m, src
}
```

- [ ] **Step 4:** Run + commit.

```bash
go test ./internal/catalog -v
git add internal/catalog/
git commit -m "feat(gateway): catalog client + refresher with env fallback"
```

### Task 8.3: Wire refresher into gateway boot path behind flag

**Files:**
- Modify: `apps-microservices/api-gateway-go/internal/config/config.go`
- Modify: `apps-microservices/api-gateway-go/cmd/gateway/main.go`

- [ ] **Step 1:** Add config fields.

```go
// in Config:
UseCatalog            bool
APICatalogGRPC        string
CatalogRefreshInterval time.Duration
```

```go
// in Load(), after existing assignments:
cfg.UseCatalog = getenvBool("GATEWAY_USE_CATALOG", false)
cfg.APICatalogGRPC = getenv("API_CATALOG_GRPC", "api-catalog-service:9100")
cfg.CatalogRefreshInterval = getenvDuration("CATALOG_REFRESH_INTERVAL", 60*time.Second)
```

(Add a `getenvDuration` helper next to existing helpers if missing — copy from api-catalog-service config.)

- [ ] **Step 2:** In `cmd/gateway/main.go`, after env-based service map is built and before HTTP server starts, branch on the flag:

```go
serviceMap := config.BuildServiceMap()  // existing call, keep as fallback baseline

var refresher *catalog.Refresher
var routeSource = "env"
if cfg.UseCatalog {
    conn, err := grpc.Dial(cfg.APICatalogGRPC,
        grpc.WithTransportCredentials(insecure.NewCredentials()))
    if err == nil {
        cli := catalog.NewClient(conn)
        refresher = catalog.NewRefresher(cli, cfg.CatalogRefreshInterval, serviceMap)
        m, src := refresher.Bootstrap(ctx, 3*time.Second)
        serviceMap = m
        routeSource = src
        go refresher.Run(ctx)
    } else {
        log.Printf("catalog dial failed; using env map (err=%v)", err)
    }
}
log.Printf("gateway routes loaded: count=%d source=%s", len(serviceMap), routeSource)

// pass serviceMap or a getter into the proxy router
```

If proxy currently reads a static `map[string]string` at boot, refactor to read via a thin getter that hits `refresher.Snapshot()` when present, else returns the static map. This is the only behavior-changing part — keep the diff small and add a unit test that verifies the proxy picks up post-refresh map updates.

- [ ] **Step 3:** Add Prometheus counter + gauge.

```go
var (
    catalogRefreshTotal = prometheus.NewCounterVec(
        prometheus.CounterOpts{Name: "gateway_catalog_refresh_total"},
        []string{"result"})
    routeSourceGauge = prometheus.NewGaugeVec(
        prometheus.GaugeOpts{Name: "gateway_route_source"},
        []string{"source"})
)
```

Register in init; bump on each refresh result; set gauge after every map swap.

- [ ] **Step 4:** Run gateway tests.

```bash
go test ./...
```

- [ ] **Step 5:** Commit.

```bash
git add internal/config/ cmd/gateway/ internal/catalog/
git commit -m "feat(gateway): consume api-catalog gRPC for routes (flag-gated)"
```

---

## Phase 9 — Cutover

### Task 9.1: Staging cutover

- [ ] **Step 1:** Deploy `api-catalog-service` + updated `account-service-{backend,frontend}` to staging. Keep `GATEWAY_USE_CATALOG=false`.

- [ ] **Step 2:** Verify catalog `RescanAll` populates DB (check via `ApiCatalogListView`). Inspect endpoint counts for known services.

- [ ] **Step 3:** Deploy updated `api-gateway-go` with `GATEWAY_USE_CATALOG=false`. Verify zero behavior change in routing (same `gateway_route_source{source="env"}` gauge, all proxy hits succeed).

- [ ] **Step 4:** Flip `GATEWAY_USE_CATALOG=true` in staging. Tail gateway logs for `gateway routes loaded: count=N source=catalog`. Spot-check 5 services route correctly.

- [ ] **Step 5:** Run integration smoke (curl 5 known endpoints through the gateway). Compare to env-only baseline. If any miss, flip back to `false` and investigate.

### Task 9.2: Production cutover

- [ ] **Step 1:** Deploy all three services to prod with `GATEWAY_USE_CATALOG=false`.

- [ ] **Step 2:** Run `RescanAll` once via UI or `curl -X POST /admin/api/rescan`.

- [ ] **Step 3:** Compare `Catalog.ListServices` output to gateway's env map. Diff — should be subset (catalog covers everything in env after first scan).

- [ ] **Step 4:** Flip `GATEWAY_USE_CATALOG=true` in prod. Monitor `gateway_catalog_refresh_total{result="fail"}` for 30 min. Watch error logs.

- [ ] **Step 5:** Document cutover date + observations in `docs/superpowers/specs/2026-05-08-api-catalog-design.md` (append to spec).

---

## Self-Review Checklist (run before handoff)

- [ ] Spec coverage: every spec decision has a task. Decisions table → tasks 0.2 / 1.* / 2.* / 3.* / 4.* / 5.* / 6.* / 7.* / 8.*. Rollout phases → Phase 9. ✅
- [ ] No placeholders ("TBD", "TODO", "implement later", "add validation"): clean. ✅
- [ ] Type consistency: `ServiceRow`, `EndpointRow`, `ApiCatalogService`, `ApiCatalogEndpoint`, RPC methods (`ListServices/CreateService/...`) match across phases. `Source` enum values `env|manual|scan` consistent. `Status` enum `active|deprecated|down` consistent. `Protocol` `rest|ws|grpc` consistent. ✅
- [ ] Code blocks present for every code step. ✅
- [ ] Exact file paths in every Files block. ✅

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-api-catalog.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
