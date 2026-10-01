# Catalog-driven APITokenVerifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-28-apitokenverifier-catalog-driven-design.md`

**Goal:** Replace the hardcoded `api-gateway-go` auth bypass (api_token.go:42-51) and `BuildExcludedRoutes` with per-service AuthPolicy + per-endpoint overrides sourced from `api-catalog-service`, CRUD'd via `account-service-backend` and `account-service-frontend`, delivered through the existing `catalog.Refresher` snapshot.

**Architecture:** New `AuthPolicy` enum (PUBLIC / BEARER / ADMIN_KEY) added to `Service` and `Endpoint` proto messages. Catalog DB extended with `auth_policy`, `public_paths`, and optional per-endpoint `auth_policy`. Gateway refresher builds an `AuthSnapshot` alongside the route map. Verifier reads the snapshot per request — no new RPC hop. Fail-open: unknown service → PUBLIC.

**Tech Stack:** Go 1.24, protobuf, grpc-go, GORM v2, MySQL, Vue 3 + TypeScript, Vitest, gin, gorilla/websocket.

**Rollout order (per spec §10):** protos → api-catalog-service → account-service-backend → account-service-frontend → api-gateway-go. Tasks below follow this order.

---

## File Structure

| Layer | File | Action |
|-------|------|--------|
| proto | `protos/grpc_stubs/api_catalog.proto` | modify — add enum, fields, RPC |
| catalog stub | `apps-microservices/api-catalog-service/internal/genproto/api_catalog/*.pb.go` | regen |
| gateway stub | `apps-microservices/api-gateway-go/internal/genproto/api_catalog/*.pb.go` | regen |
| account stub | `apps-microservices/account-service-backend/internal/genproto/api_catalog/*.pb.go` | regen |
| catalog DDL | `apps-microservices/api-catalog-service/init-db/01_schema.sql` | modify — alter columns |
| catalog seed | `apps-microservices/api-catalog-service/init-db/02_seed_auth_policy.sql` | create — backfill PUBLIC + graphdlq |
| catalog model | `apps-microservices/api-catalog-service/internal/db/models.go` | modify — AuthPolicy + PublicPaths + endpoint policy |
| catalog svc repo | `apps-microservices/api-catalog-service/internal/repository/service_repo.go` | modify — UpdateAuthPolicy + HasEndpointOverrides |
| catalog ep repo | `apps-microservices/api-catalog-service/internal/repository/endpoint_repo.go` | modify — UpdateAuthPolicy + GetByID |
| catalog mapper | `apps-microservices/api-catalog-service/internal/grpcserver/mapper.go` | modify — new fields |
| catalog server | `apps-microservices/api-catalog-service/internal/grpcserver/server.go` | modify — CreateService / UpdateService / UpdateEndpoint, HasEndpointOverrides hint |
| account client | `apps-microservices/account-service-backend/internal/api/api_catalog_client.go` | modify — add UpdateEndpoint |
| account handlers | `apps-microservices/account-service-backend/internal/api/api_catalog_handlers.go` | modify — extend req types, add endpoint update route, validation |
| account routes | `apps-microservices/account-service-backend/internal/app/routes.go` | modify — register new route |
| FE types | `apps-microservices/account-service-frontend/src/types/apiCatalog.ts` | modify — AuthPolicy, fields |
| FE api | `apps-microservices/account-service-frontend/src/api/apiCatalog.ts` | modify — updateEndpoint fn |
| FE form view | `apps-microservices/account-service-frontend/src/views/ApiCatalogFormView.vue` | modify — dropdown + public_paths editor |
| FE endpoint table | `apps-microservices/account-service-frontend/src/components/api-catalog/EndpointTable.vue` | modify — inline select |
| gw policy pkg | `apps-microservices/api-gateway-go/internal/auth/policy_snapshot.go` | create — AuthSnapshot types |
| gw catalog | `apps-microservices/api-gateway-go/internal/catalog/refresher.go` | modify — build AuthSnapshot, ListEndpoints when hint set |
| gw verifier | `apps-microservices/api-gateway-go/internal/auth/api_token.go` | modify — remove TODO short-circuit, drive from snapshot |
| gw config | `apps-microservices/api-gateway-go/internal/config/service_map.go` | modify — delete BuildExcludedRoutes |
| gw main | `apps-microservices/api-gateway-go/cmd/gateway/main.go` | modify — wire AuthSnapshot getter into verifier |

---

## Task 1: Add AuthPolicy enum + fields + UpdateEndpoint RPC to proto

**Files:**
- Modify: `protos/grpc_stubs/api_catalog.proto`

- [ ] **Step 1: Edit the proto file**

Replace the file contents with:

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
  rpc UpdateEndpoint(UpdateEndpointRequest) returns (Endpoint);
  rpc RescanAll(RescanAllRequest)         returns (RescanReport);
  rpc RescanService(RescanServiceRequest) returns (RescanReport);
}

enum Protocol   { PROTOCOL_UNSPECIFIED   = 0; REST = 1; WS = 2; GRPC = 3; }
enum Source     { SOURCE_UNSPECIFIED     = 0; ENV  = 1; MANUAL = 2; SCAN = 3; }
enum Status     { STATUS_UNSPECIFIED     = 0; ACTIVE = 1; DEPRECATED = 2; DOWN = 3; }
enum AuthPolicy { AUTH_POLICY_UNSPECIFIED = 0; PUBLIC = 1; BEARER = 2; ADMIN_KEY = 3; }

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
  AuthPolicy auth_policy = 17;
  repeated string public_paths = 18;
  bool   has_endpoint_overrides = 19;
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
  optional AuthPolicy auth_policy = 10;
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
  AuthPolicy auth_policy = 10;
  repeated string public_paths = 11;
}

message UpdateServiceRequest {
  string id = 1;
  optional string description = 2;
  optional string owner = 3;
  repeated string tags = 4;
  optional Status status = 5;
  optional AuthPolicy auth_policy = 6;
  repeated string public_paths = 7;
}

message UpdateEndpointRequest {
  string id = 1;
  optional AuthPolicy auth_policy = 2;
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

- [ ] **Step 2: Verify the file parses**

Run: `protoc --proto_path=protos/grpc_stubs --descriptor_set_out=/tmp/api_catalog.desc protos/grpc_stubs/api_catalog.proto`
Expected: command exits 0; no output.

- [ ] **Step 3: Commit**

```bash
git add protos/grpc_stubs/api_catalog.proto
git commit -m "feat(protos): add AuthPolicy enum + UpdateEndpoint RPC to api_catalog"
```

---

## Task 2: Regenerate Go stubs for catalog, gateway, account-backend

**Files:**
- Regen: `apps-microservices/api-catalog-service/internal/genproto/api_catalog/*.pb.go`
- Regen: `apps-microservices/api-gateway-go/internal/genproto/api_catalog/*.pb.go`
- Regen: `apps-microservices/account-service-backend/internal/genproto/api_catalog/*.pb.go`

- [ ] **Step 1: Check how catalog generates stubs**

Run: `cat apps-microservices/api-catalog-service/buf.gen.yaml`
Expected: shows `buf` config. If not present, use raw `protoc` per existing pattern.

- [ ] **Step 2: Regenerate each consumer's stubs**

For each consumer directory `<svc>` in `api-catalog-service`, `api-gateway-go`, `account-service-backend`, run from monorepo root:

```bash
protoc \
  --go_out=apps-microservices/<svc>/internal/genproto/api_catalog \
  --go_opt=paths=source_relative \
  --go-grpc_out=apps-microservices/<svc>/internal/genproto/api_catalog \
  --go-grpc_opt=paths=source_relative \
  --proto_path=protos/grpc_stubs \
  protos/grpc_stubs/api_catalog.proto
```

Expected: each generates `api_catalog.pb.go` + `api_catalog_grpc.pb.go`.

- [ ] **Step 3: Verify generated files compile**

Run from each service directory:
```bash
cd apps-microservices/api-catalog-service && go build ./internal/genproto/...
cd ../api-gateway-go && go build ./internal/genproto/...
cd ../account-service-backend && go build ./internal/genproto/...
```

Expected: all three build with no errors. (Repos may not yet — they reference old field names — that's fine: later tasks update them. Build only the genproto packages.)

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/*/internal/genproto/api_catalog/
git commit -m "feat(protos): regenerate api_catalog stubs for AuthPolicy"
```

---

## Task 3: api-catalog DB schema — alter tables for auth_policy + public_paths

**Files:**
- Modify: `apps-microservices/api-catalog-service/init-db/01_schema.sql`
- Create: `apps-microservices/api-catalog-service/init-db/02_seed_auth_policy.sql`
- Modify: `apps-microservices/api-catalog-service/internal/db/models.go`

- [ ] **Step 1: Update schema file** — replace contents of `01_schema.sql` with:

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
  auth_policy     TINYINT      NOT NULL DEFAULT 1,
  public_paths    JSON         NULL,
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
  auth_policy  TINYINT NULL,
  CONSTRAINT fk_endpoint_service FOREIGN KEY (service_id) REFERENCES catalog_services(id) ON DELETE CASCADE,
  KEY idx_endpoint_service (service_id),
  KEY idx_endpoint_proto   (service_id, protocol),
  KEY idx_endpoint_policy  (service_id, auth_policy)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: Create idempotent backfill** — write `02_seed_auth_policy.sql`:

```sql
USE catalog_db;

-- Backfill PUBLIC (=1) on rows that pre-date the column.
UPDATE catalog_services SET auth_policy = 1 WHERE auth_policy = 0;

-- Restore the legacy /dlq/queues bypass for graphdlq-service.
UPDATE catalog_services
SET public_paths = JSON_ARRAY('/dlq/queues')
WHERE name = 'graphdlq-service'
  AND (public_paths IS NULL OR JSON_LENGTH(public_paths) = 0);
```

- [ ] **Step 3: Update GORM model** — replace `internal/db/models.go`:

```go
package db

import "time"

type ServiceRow struct {
	ID              string `gorm:"type:char(36);primaryKey"`
	Name            string `gorm:"size:128;uniqueIndex;not null"`
	BaseURL         string `gorm:"size:512;not null"`
	Protocols       string `gorm:"size:1024;not null"`
	Source          string `gorm:"size:16;not null"`
	Status          string `gorm:"size:16;not null;default:'active'"`
	Description     string `gorm:"type:text"`
	Owner           string `gorm:"size:128"`
	Tags            string `gorm:"size:1024"`
	APIInfoURL      string `gorm:"size:512;column:api_info_url"`
	GRPCAddress     string `gorm:"size:512;column:grpc_address"`
	LastScannedAt   *time.Time
	LastScanOK      *bool  `gorm:"column:last_scan_ok"`
	LastScanError   string `gorm:"type:text;column:last_scan_error"`
	CreatedBy       string `gorm:"size:255"`
	AuthPolicy      int    `gorm:"column:auth_policy;not null;default:1"`
	PublicPaths     string `gorm:"size:2048;column:public_paths"`
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

func (ServiceRow) TableName() string { return "catalog_services" }

type EndpointRow struct {
	ID          string `gorm:"type:char(36);primaryKey"`
	ServiceID   string `gorm:"type:char(36);not null;index"`
	Protocol    string `gorm:"size:8;not null"`
	Method      string `gorm:"size:16"`
	Path        string `gorm:"size:512;not null"`
	Summary     string `gorm:"size:512"`
	OperationID string `gorm:"size:255;column:operation_id"`
	Tags        string `gorm:"size:1024"`
	Deprecated  bool   `gorm:"not null;default:false"`
	AuthPolicy  *int   `gorm:"column:auth_policy"`
}

func (EndpointRow) TableName() string { return "catalog_endpoints" }
```

- [ ] **Step 4: Build catalog-service**

Run: `cd apps-microservices/api-catalog-service && go build ./...`
Expected: compiles (existing repos/mappers don't reference new fields yet — fine, those are added in later tasks).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-catalog-service/init-db/01_schema.sql \
        apps-microservices/api-catalog-service/init-db/02_seed_auth_policy.sql \
        apps-microservices/api-catalog-service/internal/db/models.go
git commit -m "feat(api-catalog-service): add auth_policy + public_paths columns"
```

---

## Task 4: Repository tests + impl — service auth_policy + public_paths + HasEndpointOverrides

**Files:**
- Modify: `apps-microservices/api-catalog-service/internal/repository/service_repo.go`
- Modify: `apps-microservices/api-catalog-service/internal/repository/service_repo_test.go`

- [ ] **Step 1: Write failing test** — append to `service_repo_test.go`:

```go
func TestServiceRepo_AuthPolicyDefault(t *testing.T) {
	repo, _ := newServiceRepo(t)
	row := &db.ServiceRow{ID: "auth-default", Name: "x-service", BaseURL: "http://x", Protocols: "[]", Source: "manual", Status: "active"}
	if err := repo.Create(row); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetByID("auth-default")
	if err != nil {
		t.Fatal(err)
	}
	if got.AuthPolicy != 1 { // PUBLIC
		t.Fatalf("default auth_policy = %d, want 1 (PUBLIC)", got.AuthPolicy)
	}
}

func TestServiceRepo_UpdateAuthPolicy(t *testing.T) {
	repo, _ := newServiceRepo(t)
	row := &db.ServiceRow{ID: "auth-update", Name: "y-service", BaseURL: "http://y", Protocols: "[]", Source: "manual", Status: "active"}
	_ = repo.Create(row)
	if err := repo.Update("auth-update", map[string]any{"auth_policy": 2, "public_paths": `["/health"]`}); err != nil {
		t.Fatal(err)
	}
	got, _ := repo.GetByID("auth-update")
	if got.AuthPolicy != 2 || got.PublicPaths != `["/health"]` {
		t.Fatalf("got policy=%d paths=%q; want 2 + /health JSON", got.AuthPolicy, got.PublicPaths)
	}
}

func TestServiceRepo_HasEndpointOverrides(t *testing.T) {
	repo, gdb := newServiceRepo(t)
	row := &db.ServiceRow{ID: "svc-h", Name: "h-service", BaseURL: "http://h", Protocols: "[]", Source: "manual", Status: "active"}
	_ = repo.Create(row)
	got, err := repo.HasEndpointOverrides("svc-h")
	if err != nil || got {
		t.Fatalf("empty endpoints: hasOverrides=%v err=%v; want false,nil", got, err)
	}
	p := 2
	_ = gdb.Create(&db.EndpointRow{ID: "ep1", ServiceID: "svc-h", Protocol: "rest", Path: "/", AuthPolicy: &p}).Error
	got, _ = repo.HasEndpointOverrides("svc-h")
	if !got {
		t.Fatal("with one override row: want true")
	}
}
```

If `newServiceRepo` helper isn't shared with endpoint tests, add it:
```go
func newServiceRepo(t *testing.T) (*ServiceRepo, *gorm.DB) {
	t.Helper()
	gdb := openTestDB(t) // existing helper in repo_test.go
	return NewServiceRepo(gdb), gdb
}
```

- [ ] **Step 2: Run tests — verify failure**

Run: `cd apps-microservices/api-catalog-service && go test ./internal/repository/ -run "AuthPolicyDefault|UpdateAuthPolicy|HasEndpointOverrides" -v`
Expected: FAIL — `repo.HasEndpointOverrides undefined`; default test may pass if GORM honors the `default:1` tag.

- [ ] **Step 3: Add `HasEndpointOverrides`** — append to `service_repo.go`:

```go
func (r *ServiceRepo) HasEndpointOverrides(serviceID string) (bool, error) {
	var count int64
	err := r.g.Table("catalog_endpoints").
		Where("service_id = ? AND auth_policy IS NOT NULL", serviceID).
		Count(&count).Error
	if err != nil {
		return false, err
	}
	return count > 0, nil
}
```

- [ ] **Step 4: Re-run tests**

Run: `go test ./internal/repository/ -run "AuthPolicyDefault|UpdateAuthPolicy|HasEndpointOverrides" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-catalog-service/internal/repository/service_repo.go \
        apps-microservices/api-catalog-service/internal/repository/service_repo_test.go
git commit -m "feat(api-catalog-service): repo support for auth_policy + override detection"
```

---

## Task 5: Endpoint repo — UpdateAuthPolicy + GetByID

**Files:**
- Modify: `apps-microservices/api-catalog-service/internal/repository/endpoint_repo.go`
- Modify: `apps-microservices/api-catalog-service/internal/repository/endpoint_repo_test.go`

- [ ] **Step 1: Write failing tests** — append to `endpoint_repo_test.go`:

```go
func TestEndpointRepo_UpdateAuthPolicy_Set(t *testing.T) {
	repo, gdb := newEndpointRepo(t)
	_ = gdb.Create(&db.EndpointRow{ID: "ep-set", ServiceID: "svc", Protocol: "rest", Path: "/a"}).Error
	policy := 2
	if err := repo.UpdateAuthPolicy("ep-set", &policy); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetByID("ep-set")
	if err != nil || got.AuthPolicy == nil || *got.AuthPolicy != 2 {
		t.Fatalf("got=%+v err=%v; want policy=2", got, err)
	}
}

func TestEndpointRepo_UpdateAuthPolicy_Clear(t *testing.T) {
	repo, gdb := newEndpointRepo(t)
	policy := 3
	_ = gdb.Create(&db.EndpointRow{ID: "ep-clr", ServiceID: "svc", Protocol: "rest", Path: "/b", AuthPolicy: &policy}).Error
	if err := repo.UpdateAuthPolicy("ep-clr", nil); err != nil {
		t.Fatal(err)
	}
	got, _ := repo.GetByID("ep-clr")
	if got.AuthPolicy != nil {
		t.Fatalf("got policy=%d; want nil after clear", *got.AuthPolicy)
	}
}

func TestEndpointRepo_GetByID_NotFound(t *testing.T) {
	repo, _ := newEndpointRepo(t)
	if _, err := repo.GetByID("nope"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("got err=%v; want ErrNotFound", err)
	}
}
```

If `newEndpointRepo` doesn't exist, add:
```go
func newEndpointRepo(t *testing.T) (*EndpointRepo, *gorm.DB) {
	t.Helper()
	gdb := openTestDB(t)
	return NewEndpointRepo(gdb), gdb
}
```

- [ ] **Step 2: Run tests — verify failure**

Run: `cd apps-microservices/api-catalog-service && go test ./internal/repository/ -run "UpdateAuthPolicy|GetByID_NotFound" -v`
Expected: FAIL — methods undefined.

- [ ] **Step 3: Implement** — append to `endpoint_repo.go`:

```go
func (r *EndpointRepo) GetByID(id string) (*db.EndpointRow, error) {
	var ep db.EndpointRow
	if err := r.g.First(&ep, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return &ep, nil
}

func (r *EndpointRepo) UpdateAuthPolicy(id string, policy *int) error {
	res := r.g.Model(&db.EndpointRow{}).
		Where("id = ?", id).
		Update("auth_policy", policy) // GORM writes NULL when policy is nil
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}
```

Add `import "errors"` to endpoint_repo.go if not already present.

- [ ] **Step 4: Re-run**

Run: `go test ./internal/repository/ -v`
Expected: all repo tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-catalog-service/internal/repository/endpoint_repo.go \
        apps-microservices/api-catalog-service/internal/repository/endpoint_repo_test.go
git commit -m "feat(api-catalog-service): endpoint repo UpdateAuthPolicy + GetByID"
```

---

## Task 6: Mapper — round-trip new fields

**Files:**
- Modify: `apps-microservices/api-catalog-service/internal/grpcserver/mapper.go`
- Modify: `apps-microservices/api-catalog-service/internal/grpcserver/mapper_test.go`

- [ ] **Step 1: Write failing test** — append to `mapper_test.go`:

```go
func TestServiceRowToProto_AuthPolicy(t *testing.T) {
	row := db.ServiceRow{
		ID: "1", Name: "n", BaseURL: "http://x", Protocols: "[]",
		Source: "manual", Status: "active",
		AuthPolicy:  2, // BEARER
		PublicPaths: `["/health","/ready"]`,
	}
	got := ServiceRowToProto(row)
	if got.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("auth_policy=%v; want BEARER", got.GetAuthPolicy())
	}
	if want := []string{"/health", "/ready"}; !reflect.DeepEqual(got.GetPublicPaths(), want) {
		t.Fatalf("public_paths=%v; want %v", got.GetPublicPaths(), want)
	}
}

func TestEndpointRowToProto_AuthPolicy_Override(t *testing.T) {
	policy := 3 // ADMIN_KEY
	row := db.EndpointRow{ID: "e", ServiceID: "s", Protocol: "rest", Path: "/x", AuthPolicy: &policy}
	got := EndpointRowToProto(row)
	if got.GetAuthPolicy() != pb.AuthPolicy_ADMIN_KEY {
		t.Fatalf("auth_policy=%v; want ADMIN_KEY", got.GetAuthPolicy())
	}
}

func TestEndpointRowToProto_AuthPolicy_Unset(t *testing.T) {
	row := db.EndpointRow{ID: "e", ServiceID: "s", Protocol: "rest", Path: "/x", AuthPolicy: nil}
	got := EndpointRowToProto(row)
	if got.AuthPolicy != nil {
		t.Fatalf("expected proto AuthPolicy to remain nil for unset override")
	}
}
```

Add `import "reflect"` if missing.

- [ ] **Step 2: Run — verify failure**

Run: `go test ./internal/grpcserver/ -run "RowToProto_AuthPolicy" -v`
Expected: FAIL — mapper doesn't read new fields.

- [ ] **Step 3: Update mapper** — replace `ServiceRowToProto` body to also fill `auth_policy` + `public_paths`, and update `EndpointRowToProto` for optional `auth_policy`. Add helpers below:

```go
func ServiceRowToProto(r db.ServiceRow) *pb.Service {
	var protos []string
	_ = json.Unmarshal([]byte(r.Protocols), &protos)
	var tags []string
	if r.Tags != "" {
		_ = json.Unmarshal([]byte(r.Tags), &tags)
	}
	var publicPaths []string
	if r.PublicPaths != "" {
		_ = json.Unmarshal([]byte(r.PublicPaths), &publicPaths)
	}
	pbProtos := make([]pb.Protocol, 0, len(protos))
	for _, s := range protos {
		pbProtos = append(pbProtos, protoFromStr(s))
	}
	out := &pb.Service{
		Id: r.ID, Name: r.Name, BaseUrl: r.BaseURL,
		Protocols:     pbProtos,
		Source:        sourceFromStr(r.Source),
		Status:        statusFromStr(r.Status),
		Description:   r.Description,
		Owner:         r.Owner,
		Tags:          tags,
		ApiInfoUrl:    r.APIInfoURL,
		GrpcAddress:   r.GRPCAddress,
		LastScanError: r.LastScanError,
		AuthPolicy:    authPolicyFromInt(r.AuthPolicy),
		PublicPaths:   publicPaths,
		CreatedAt:     timestamppb.New(r.CreatedAt),
		UpdatedAt:     timestamppb.New(r.UpdatedAt),
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
	out := &pb.Endpoint{
		Id: r.ID, ServiceId: r.ServiceID, Method: r.Method, Path: r.Path,
		Summary: r.Summary, OperationId: r.OperationID, Tags: tags,
		Deprecated: r.Deprecated, Protocol: protoFromStr(r.Protocol),
	}
	if r.AuthPolicy != nil {
		p := authPolicyFromInt(*r.AuthPolicy)
		out.AuthPolicy = &p
	}
	return out
}

// authPolicyFromInt maps the DB TINYINT to the proto enum.
// Anything outside the known set (incl. 0/UNSPECIFIED) coerces to PUBLIC,
// matching the spec fail-open default.
func authPolicyFromInt(v int) pb.AuthPolicy {
	switch v {
	case 1:
		return pb.AuthPolicy_PUBLIC
	case 2:
		return pb.AuthPolicy_BEARER
	case 3:
		return pb.AuthPolicy_ADMIN_KEY
	}
	return pb.AuthPolicy_PUBLIC
}

// AuthPolicyToInt maps the proto enum to the DB TINYINT.
// UNSPECIFIED stores as 1 (PUBLIC) per the migration/seed contract.
func AuthPolicyToInt(p pb.AuthPolicy) int {
	switch p {
	case pb.AuthPolicy_PUBLIC:
		return 1
	case pb.AuthPolicy_BEARER:
		return 2
	case pb.AuthPolicy_ADMIN_KEY:
		return 3
	}
	return 1
}
```

- [ ] **Step 4: Re-run**

Run: `go test ./internal/grpcserver/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-catalog-service/internal/grpcserver/mapper.go \
        apps-microservices/api-catalog-service/internal/grpcserver/mapper_test.go
git commit -m "feat(api-catalog-service): mapper round-trips AuthPolicy + public_paths"
```

---

## Task 7: gRPC server — extend Create/Update + add UpdateEndpoint + hint

**Files:**
- Modify: `apps-microservices/api-catalog-service/internal/grpcserver/server.go`
- Modify: `apps-microservices/api-catalog-service/internal/grpcserver/server_test.go`

- [ ] **Step 1: Write failing tests** — append to `server_test.go`:

```go
func TestServer_CreateService_WithAuthPolicy(t *testing.T) {
	srv := newTestServer(t)
	got, err := srv.CreateService(context.Background(), &pb.CreateServiceRequest{
		Name:        "alpha",
		BaseUrl:     "http://alpha",
		Protocols:   []pb.Protocol{pb.Protocol_REST},
		AuthPolicy:  pb.AuthPolicy_BEARER,
		PublicPaths: []string{"/health"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if got.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("auth_policy=%v; want BEARER", got.GetAuthPolicy())
	}
	if diff := cmp.Diff([]string{"/health"}, got.GetPublicPaths()); diff != "" {
		t.Fatalf("public_paths mismatch: %s", diff)
	}
}

func TestServer_UpdateService_AuthPolicyOnly(t *testing.T) {
	srv := newTestServer(t)
	created, _ := srv.CreateService(context.Background(), &pb.CreateServiceRequest{Name: "beta", BaseUrl: "http://beta", Protocols: []pb.Protocol{pb.Protocol_REST}})
	policy := pb.AuthPolicy_ADMIN_KEY
	updated, err := srv.UpdateService(context.Background(), &pb.UpdateServiceRequest{
		Id:         created.GetId(),
		AuthPolicy: &policy,
	})
	if err != nil {
		t.Fatal(err)
	}
	if updated.GetAuthPolicy() != pb.AuthPolicy_ADMIN_KEY {
		t.Fatalf("auth_policy=%v; want ADMIN_KEY", updated.GetAuthPolicy())
	}
}

func TestServer_UpdateEndpoint_SetThenClear(t *testing.T) {
	srv := newTestServer(t)
	created, _ := srv.CreateService(context.Background(), &pb.CreateServiceRequest{Name: "gamma", BaseUrl: "http://gamma", Protocols: []pb.Protocol{pb.Protocol_REST}})
	epRow := db.EndpointRow{ID: "ep-1", ServiceID: created.GetId(), Protocol: "rest", Path: "/x"}
	_ = srv.deps().Endpoints.ReplaceForService(created.GetId(), []db.EndpointRow{epRow})

	bearer := pb.AuthPolicy_BEARER
	got, err := srv.UpdateEndpoint(context.Background(), &pb.UpdateEndpointRequest{Id: "ep-1", AuthPolicy: &bearer})
	if err != nil {
		t.Fatal(err)
	}
	if got.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("set: got=%v; want BEARER", got.GetAuthPolicy())
	}

	got2, err := srv.UpdateEndpoint(context.Background(), &pb.UpdateEndpointRequest{Id: "ep-1", AuthPolicy: nil})
	if err != nil {
		t.Fatal(err)
	}
	if got2.AuthPolicy != nil {
		t.Fatalf("clear: got=%v; want nil", got2.GetAuthPolicy())
	}
}

func TestServer_ListServices_HasEndpointOverrides(t *testing.T) {
	srv := newTestServer(t)
	a, _ := srv.CreateService(context.Background(), &pb.CreateServiceRequest{Name: "a", BaseUrl: "http://a", Protocols: []pb.Protocol{pb.Protocol_REST}})
	_, _ = srv.CreateService(context.Background(), &pb.CreateServiceRequest{Name: "b", BaseUrl: "http://b", Protocols: []pb.Protocol{pb.Protocol_REST}})
	policy := 2
	_ = srv.deps().Endpoints.(*repository.EndpointRepo).ReplaceForService(a.GetId(), []db.EndpointRow{{ID: "ep-a", ServiceID: a.GetId(), Protocol: "rest", Path: "/", AuthPolicy: &policy}})

	resp, _ := srv.ListServices(context.Background(), &pb.ListServicesRequest{Limit: 10})
	var foundA, foundB bool
	for _, s := range resp.GetItems() {
		if s.GetName() == "a-service" {
			foundA = s.GetHasEndpointOverrides()
		}
		if s.GetName() == "b-service" {
			foundB = !s.GetHasEndpointOverrides()
		}
	}
	if !foundA || !foundB {
		t.Fatalf("expected a-service hasOverrides=true and b-service=false")
	}
}
```

Add `srv.deps()` accessor in test helper if needed; if `newTestServer` already exposes deps, use that path. Add `"github.com/google/go-cmp/cmp"` import if not already in go.mod (it is — used by other tests in the service).

- [ ] **Step 2: Run — verify failure**

Run: `go test ./internal/grpcserver/ -run "CreateService_WithAuthPolicy|UpdateService_AuthPolicyOnly|UpdateEndpoint_SetThenClear|ListServices_HasEndpointOverrides" -v`
Expected: FAIL — UpdateEndpoint method undefined; CreateService ignores new fields; ListServices doesn't compute hint.

- [ ] **Step 3: Update server** — apply these surgical edits to `server.go`:

In `CreateService`, after `tagsJSON` is computed, persist new fields:
```go
var pathsJSON string
if len(req.GetPublicPaths()) > 0 {
	b, _ := json.Marshal(req.GetPublicPaths())
	pathsJSON = string(b)
}
row := &db.ServiceRow{
	ID: uuid.NewString(), Name: name, BaseURL: req.GetBaseUrl(),
	Protocols: string(pj), Source: "manual", Status: "active",
	Description: req.GetDescription(), Owner: req.GetOwner(),
	Tags: tagsJSON, APIInfoURL: req.GetApiInfoUrl(), GRPCAddress: req.GetGrpcAddress(),
	CreatedBy:   req.GetCreatedBy(),
	AuthPolicy:  AuthPolicyToInt(req.GetAuthPolicy()),
	PublicPaths: pathsJSON,
}
```

In `UpdateService`, before the `if len(fields) == 0` guard, add:
```go
if req.AuthPolicy != nil {
	fields["auth_policy"] = AuthPolicyToInt(req.GetAuthPolicy())
}
if req.PublicPaths != nil {
	b, _ := json.Marshal(req.GetPublicPaths())
	fields["public_paths"] = string(b)
}
```

After the existing methods in `server.go`, add `UpdateEndpoint`:
```go
func (s *Server) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) {
	if req.GetId() == "" {
		return nil, status.Error(codes.InvalidArgument, "id required")
	}
	var policy *int
	if req.AuthPolicy != nil {
		p := AuthPolicyToInt(req.GetAuthPolicy())
		policy = &p
	}
	if err := s.d.Endpoints.UpdateAuthPolicy(req.GetId(), policy); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			return nil, status.Error(codes.NotFound, "endpoint not found")
		}
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	row, err := s.d.Endpoints.GetByID(req.GetId())
	if err != nil {
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	return EndpointRowToProto(*row), nil
}
```

In `ListServices`, after building each `out.Items` entry, set the hint:
```go
out := &pb.ListServicesResponse{Total: total}
for _, r := range items {
	pbSvc := ServiceRowToProto(r)
	has, _ := s.d.Services.HasEndpointOverrides(r.ID)
	pbSvc.HasEndpointOverrides = has
	out.Items = append(out.Items, pbSvc)
}
return out, nil
```

Update `Deps` struct to use the concrete `*repository.EndpointRepo` type (already in use). No interface change needed unless tests inject a mock — keep as-is.

- [ ] **Step 4: Re-run tests**

Run: `go test ./internal/grpcserver/ -v`
Expected: PASS for all four new tests + existing tests still green.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-catalog-service/internal/grpcserver/server.go \
        apps-microservices/api-catalog-service/internal/grpcserver/server_test.go
git commit -m "feat(api-catalog-service): wire AuthPolicy through Create/Update + add UpdateEndpoint"
```

---

## Task 8: account-service-backend — request types + validation + parser

**Files:**
- Modify: `apps-microservices/account-service-backend/internal/api/api_catalog_handlers.go`
- Modify: `apps-microservices/account-service-backend/internal/api/api_catalog_handlers_test.go`

- [ ] **Step 1: Write failing tests** — append to `api_catalog_handlers_test.go`:

```go
func TestCreate_RejectsInvalidAuthPolicy(t *testing.T) {
	h := newHandler(t, fakeCatalog{})
	body := strings.NewReader(`{"name":"x","baseUrl":"http://x","authPolicy":"banana"}`)
	req := httptest.NewRequest("POST", "/api/v1/admin/api", body)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("status=%d; want 400", w.Code)
	}
	if !strings.Contains(w.Body.String(), "invalid_auth_policy") {
		t.Fatalf("body=%q; want invalid_auth_policy", w.Body.String())
	}
}

func TestCreate_RejectsInvalidPublicPath(t *testing.T) {
	cases := []string{`["no-slash"]`, `["/with/*"]`, `["/with?q"]`, `[""]`}
	for _, jsonArr := range cases {
		h := newHandler(t, fakeCatalog{})
		body := strings.NewReader(`{"name":"x","baseUrl":"http://x","publicPaths":` + jsonArr + `}`)
		req := httptest.NewRequest("POST", "/api/v1/admin/api", body)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		if w.Code != http.StatusBadRequest {
			t.Fatalf("paths=%s status=%d; want 400", jsonArr, w.Code)
		}
	}
}

func TestCreate_NormalizesPublicPath_StripTrailingSlash(t *testing.T) {
	fake := &fakeCatalog{}
	h := newHandler(t, fake)
	body := strings.NewReader(`{"name":"x","baseUrl":"http://x","authPolicy":"bearer","publicPaths":["/foo/"]}`)
	req := httptest.NewRequest("POST", "/api/v1/admin/api", body)
	h.ServeHTTP(httptest.NewRecorder(), req)
	if got := fake.lastCreate.GetPublicPaths(); !reflect.DeepEqual(got, []string{"/foo"}) {
		t.Fatalf("paths=%v; want [/foo]", got)
	}
	if fake.lastCreate.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("policy=%v; want BEARER", fake.lastCreate.GetAuthPolicy())
	}
}

func TestUpdateEndpoint_RoundTrip(t *testing.T) {
	fake := &fakeCatalog{}
	h := newHandler(t, fake)
	body := strings.NewReader(`{"authPolicy":"bearer"}`)
	req := httptest.NewRequest("PUT", "/api/v1/admin/api/svc-1/endpoints/ep-1", body)
	req.SetPathValue("id", "svc-1")
	req.SetPathValue("endpoint_id", "ep-1")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s; want 200", w.Code, w.Body.String())
	}
	if fake.lastUpdateEndpoint.GetId() != "ep-1" || fake.lastUpdateEndpoint.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("got=%+v; want id=ep-1 BEARER", fake.lastUpdateEndpoint)
	}
}

func TestUpdateEndpoint_ClearWithNull(t *testing.T) {
	fake := &fakeCatalog{}
	h := newHandler(t, fake)
	body := strings.NewReader(`{"authPolicy":null}`)
	req := httptest.NewRequest("PUT", "/api/v1/admin/api/svc-1/endpoints/ep-1", body)
	req.SetPathValue("id", "svc-1")
	req.SetPathValue("endpoint_id", "ep-1")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d; want 200", w.Code)
	}
	if fake.lastUpdateEndpoint.AuthPolicy != nil {
		t.Fatalf("expected nil AuthPolicy on clear")
	}
}
```

If `fakeCatalog` already exists in the test file, extend it; otherwise add:
```go
type fakeCatalog struct {
	lastCreate         *pb.CreateServiceRequest
	lastUpdate         *pb.UpdateServiceRequest
	lastUpdateEndpoint *pb.UpdateEndpointRequest
}
func (f *fakeCatalog) ListServices(ctx context.Context, l, o int, fil string) (*pb.ListServicesResponse, error) { return &pb.ListServicesResponse{}, nil }
func (f *fakeCatalog) GetService(ctx context.Context, id string) (*pb.Service, error) { return &pb.Service{Id: id}, nil }
func (f *fakeCatalog) ListEndpoints(ctx context.Context, id string, p pb.Protocol) (*pb.ListEndpointsResponse, error) { return &pb.ListEndpointsResponse{}, nil }
func (f *fakeCatalog) Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) { f.lastCreate = req; return &pb.Service{Id: "new"}, nil }
func (f *fakeCatalog) Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) { f.lastUpdate = req; return &pb.Service{Id: req.GetId()}, nil }
func (f *fakeCatalog) Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error) { return &pb.DeleteServiceResponse{Deleted: true}, nil }
func (f *fakeCatalog) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) { f.lastUpdateEndpoint = req; return &pb.Endpoint{Id: req.GetId()}, nil }
func (f *fakeCatalog) RescanAll(ctx context.Context) (*pb.RescanReport, error) { return &pb.RescanReport{}, nil }
func (f *fakeCatalog) RescanService(ctx context.Context, id string) (*pb.RescanReport, error) { return &pb.RescanReport{}, nil }

func newHandler(t *testing.T, c CatalogClientIface) http.Handler {
	t.Helper()
	return NewAPICatalogHandler(APICatalogDeps{Client: c})
}
```

- [ ] **Step 2: Run — verify failure**

Run: `cd apps-microservices/account-service-backend && go test ./internal/api/ -run "Create_Rejects|NormalizesPublicPath|UpdateEndpoint_" -v`
Expected: FAIL — types missing fields, validation not present, endpoint route 405.

- [ ] **Step 3: Extend request types** — replace the existing `createReq` / `updateReq` blocks in `api_catalog_handlers.go`:

```go
type createReq struct {
	Name        string   `json:"name"`
	BaseUrl     string   `json:"baseUrl"`
	Protocols   []string `json:"protocols"`
	Description string   `json:"description"`
	Owner       string   `json:"owner"`
	Tags        []string `json:"tags"`
	ApiInfoUrl  string   `json:"apiInfoUrl"`
	GrpcAddress string   `json:"grpcAddress"`
	AuthPolicy  string   `json:"authPolicy,omitempty"`
	PublicPaths []string `json:"publicPaths,omitempty"`
}

type updateReq struct {
	Description *string  `json:"description,omitempty"`
	Owner       *string  `json:"owner,omitempty"`
	Tags        []string `json:"tags"`
	Status      *string  `json:"status,omitempty"`
	AuthPolicy  *string  `json:"authPolicy,omitempty"`
	PublicPaths []string `json:"publicPaths,omitempty"`
}

type updateEndpointReq struct {
	AuthPolicy *string `json:"authPolicy"` // missing field = leave unchanged is unsupported; spec uses explicit set/null
}
```

Add helpers:
```go
func authPolicyFromString(s string) (pb.AuthPolicy, error) {
	switch strings.ToLower(s) {
	case "", "public":
		return pb.AuthPolicy_PUBLIC, nil
	case "bearer":
		return pb.AuthPolicy_BEARER, nil
	case "admin-key":
		return pb.AuthPolicy_ADMIN_KEY, nil
	}
	return pb.AuthPolicy_AUTH_POLICY_UNSPECIFIED, fmt.Errorf("invalid_auth_policy")
}

func authPolicyToString(p pb.AuthPolicy) string {
	switch p {
	case pb.AuthPolicy_PUBLIC:
		return "public"
	case pb.AuthPolicy_BEARER:
		return "bearer"
	case pb.AuthPolicy_ADMIN_KEY:
		return "admin-key"
	}
	return ""
}

// normalizePublicPath validates and canonicalizes a public_path entry per spec §6.3.
// Returns the canonical form (leading "/", no trailing "/", no wildcards) or an error.
func normalizePublicPath(p string) (string, error) {
	p = strings.TrimSpace(p)
	if p == "" || !strings.HasPrefix(p, "/") || strings.ContainsAny(p, "*?") {
		return "", fmt.Errorf("invalid_public_path")
	}
	p = strings.TrimRight(p, "/")
	if p == "" {
		return "", fmt.Errorf("invalid_public_path")
	}
	return p, nil
}

func normalizePublicPaths(in []string) ([]string, error) {
	out := make([]string, 0, len(in))
	for _, p := range in {
		np, err := normalizePublicPath(p)
		if err != nil {
			return nil, err
		}
		out = append(out, np)
	}
	return out, nil
}
```

Add `"fmt"` to imports if not present.

Update `create` handler to populate the new request fields (insert before the existing `req := &pb.CreateServiceRequest{...}` block):
```go
policy, err := authPolicyFromString(body.AuthPolicy)
if err != nil {
	http.Error(w, `{"error":"invalid_auth_policy"}`, http.StatusBadRequest)
	return
}
paths, err := normalizePublicPaths(body.PublicPaths)
if err != nil {
	http.Error(w, `{"error":"invalid_public_path"}`, http.StatusBadRequest)
	return
}
```
Then in the `req := &pb.CreateServiceRequest{...}` literal append:
```go
AuthPolicy:  policy,
PublicPaths: paths,
```

Update `update` handler similarly — after JSON decode, before `req := &pb.UpdateServiceRequest{...}`:
```go
var pbPolicy *pb.AuthPolicy
if body.AuthPolicy != nil {
	p, err := authPolicyFromString(*body.AuthPolicy)
	if err != nil {
		http.Error(w, `{"error":"invalid_auth_policy"}`, http.StatusBadRequest)
		return
	}
	pbPolicy = &p
}
var normalizedPaths []string
if body.PublicPaths != nil {
	np, err := normalizePublicPaths(body.PublicPaths)
	if err != nil {
		http.Error(w, `{"error":"invalid_public_path"}`, http.StatusBadRequest)
		return
	}
	normalizedPaths = np
}
```
Append to the `req` literal:
```go
AuthPolicy:  pbPolicy,
PublicPaths: normalizedPaths,
```

Extend `serviceToJSON` to emit new fields:
```go
out["authPolicy"] = authPolicyToString(s.GetAuthPolicy())
out["publicPaths"] = s.GetPublicPaths()
out["hasEndpointOverrides"] = s.GetHasEndpointOverrides()
```

Extend `endpointToJSON`:
```go
if s := s.GetAuthPolicy(); s != pb.AuthPolicy_AUTH_POLICY_UNSPECIFIED {
	out["authPolicy"] = authPolicyToString(s)
}
```
(Be careful with variable shadowing; rename inner `s` to `pol` if compiler complains.)

Add new dispatch + handler to the mux switch in `ServeHTTP`:
```go
endpointID := r.PathValue("endpoint_id")
switch {
// ... existing cases ...
case id != "" && endpointID != "" && r.Method == http.MethodPut:
	h.updateEndpoint(w, r, id, endpointID)
// ... default ...
}
```

Add the method:
```go
func (h *apiCatalogHandler) updateEndpoint(w http.ResponseWriter, r *http.Request, serviceID, endpointID string) {
	var body updateEndpointReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, `{"error":"invalid_json"}`, http.StatusBadRequest)
		return
	}
	req := &pb.UpdateEndpointRequest{Id: endpointID}
	if body.AuthPolicy != nil {
		p, err := authPolicyFromString(*body.AuthPolicy)
		if err != nil {
			http.Error(w, `{"error":"invalid_auth_policy"}`, http.StatusBadRequest)
			return
		}
		req.AuthPolicy = &p
	}
	ep, err := h.d.Client.UpdateEndpoint(r.Context(), req)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	h.audit(r.Context(), actorEmail(r), "catalog.update_endpoint", endpointID)
	writeJSON(w, http.StatusOK, endpointToJSON(ep))
}
```

Update `CatalogClientIface` to declare the new method:
```go
type CatalogClientIface interface {
	// ... existing ...
	UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error)
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./internal/api/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-backend/internal/api/api_catalog_handlers.go \
        apps-microservices/account-service-backend/internal/api/api_catalog_handlers_test.go
git commit -m "feat(account-service-backend): auth policy validation + endpoint update handler"
```

---

## Task 9: account-service-backend — CatalogClient.UpdateEndpoint + route

**Files:**
- Modify: `apps-microservices/account-service-backend/internal/api/api_catalog_client.go`
- Modify: `apps-microservices/account-service-backend/internal/api/api_catalog_client_test.go`
- Modify: `apps-microservices/account-service-backend/internal/app/routes.go`

- [ ] **Step 1: Add client method** — append to `api_catalog_client.go`:

```go
func (c *CatalogClient) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) {
	return c.cli.UpdateEndpoint(c.authCtx(ctx), req)
}
```

- [ ] **Step 2: Add client smoke test** — append to `api_catalog_client_test.go`:

```go
func TestCatalogClient_UpdateEndpoint_PropagatesAdminKey(t *testing.T) {
	srv, stop := startTestCatalog(t) // existing helper used by other client tests
	defer stop()
	c := NewCatalogClient(srv.Conn(), "k1")
	bearer := pb.AuthPolicy_BEARER
	_, err := c.UpdateEndpoint(context.Background(), &pb.UpdateEndpointRequest{Id: srv.SeedEndpoint(), AuthPolicy: &bearer})
	if err != nil {
		t.Fatal(err)
	}
	if got := srv.LastMD().Get("authorization"); len(got) == 0 || got[0] != "Bearer k1" {
		t.Fatalf("md=%v; want Bearer k1", got)
	}
}
```

If `startTestCatalog` doesn't exist in this codebase, replace with a `grpcmock`/bufconn-based mini-server matching the existing pattern in `api_catalog_client_test.go`. If the file doesn't currently exist, skip this test entry (the handler tests in Task 8 cover the call shape).

- [ ] **Step 3: Run client tests**

Run: `cd apps-microservices/account-service-backend && go test ./internal/api/ -run "CatalogClient_" -v`
Expected: PASS (or "no tests to run" if file omitted — fine).

- [ ] **Step 4: Register HTTP route** — in `internal/app/routes.go`, after the existing catalog routes block (around line 147), add:

```go
mux.Handle("PUT /api/v1/admin/api/{id}/endpoints/{endpoint_id}", requireAuth(catalogHandler))
```

- [ ] **Step 5: Build**

Run: `cd apps-microservices/account-service-backend && go build ./...`
Expected: clean build.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-backend/internal/api/api_catalog_client.go \
        apps-microservices/account-service-backend/internal/api/api_catalog_client_test.go \
        apps-microservices/account-service-backend/internal/app/routes.go
git commit -m "feat(account-service-backend): expose PUT /api/v1/admin/api/{id}/endpoints/{ep_id}"
```

---

## Task 10: Frontend — types + api client function

**Files:**
- Modify: `apps-microservices/account-service-frontend/src/types/apiCatalog.ts`
- Modify: `apps-microservices/account-service-frontend/src/api/apiCatalog.ts`
- Modify: `apps-microservices/account-service-frontend/src/api/apiCatalog.spec.ts`

- [ ] **Step 1: Write failing test** — append to `apiCatalog.spec.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { updateEndpoint } from './apiCatalog'

describe('updateEndpoint', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))
  })
  afterEach(() => vi.restoreAllMocks())

  it('PUTs to /api/v1/admin/api/{id}/endpoints/{ep_id}', async () => {
    await updateEndpoint('svc-1', 'ep-1', { authPolicy: 'bearer' })
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/admin/api/svc-1/endpoints/ep-1'),
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ authPolicy: 'bearer' }) }),
    )
  })

  it('sends null to clear override', async () => {
    await updateEndpoint('svc-1', 'ep-1', { authPolicy: null })
    expect(fetch).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ body: JSON.stringify({ authPolicy: null }) }),
    )
  })
})
```

- [ ] **Step 2: Run — verify failure**

Run: `cd apps-microservices/account-service-frontend && npx vitest run src/api/apiCatalog.spec.ts`
Expected: FAIL — `updateEndpoint` not exported.

- [ ] **Step 3: Extend types** — edit `types/apiCatalog.ts`:

```ts
export type AuthPolicy = 'public' | 'bearer' | 'admin-key'

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
  authPolicy?: AuthPolicy
  publicPaths?: string[]
  hasEndpointOverrides?: boolean
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
  authPolicy?: AuthPolicy
}

// keep ListResp / DetailResp / RescanReport unchanged

export interface CreateApiRequest {
  name: string
  baseUrl: string
  protocols: Protocol[]
  description?: string
  owner?: string
  tags?: string[]
  apiInfoUrl?: string
  grpcAddress?: string
  authPolicy?: AuthPolicy
  publicPaths?: string[]
}

export interface UpdateApiRequest {
  description?: string
  owner?: string
  tags?: string[]
  status?: Status
  authPolicy?: AuthPolicy
  publicPaths?: string[]
}

export interface UpdateEndpointRequest {
  authPolicy: AuthPolicy | null
}
```

- [ ] **Step 4: Add api function** — append to `api/apiCatalog.ts`:

```ts
import type {
  // ... existing imports unchanged
  ApiCatalogEndpoint,
  UpdateEndpointRequest,
} from '@/types/apiCatalog'

export function updateEndpoint(
  serviceId: string,
  endpointId: string,
  payload: UpdateEndpointRequest,
) {
  return api<ApiCatalogEndpoint>(
    `${base}/${encodeURIComponent(serviceId)}/endpoints/${encodeURIComponent(endpointId)}`,
    { method: 'PUT', body: payload },
  )
}
```

- [ ] **Step 5: Re-run tests**

Run: `npx vitest run src/api/apiCatalog.spec.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/account-service-frontend/src/types/apiCatalog.ts \
        apps-microservices/account-service-frontend/src/api/apiCatalog.ts \
        apps-microservices/account-service-frontend/src/api/apiCatalog.spec.ts
git commit -m "feat(account-service-frontend): AuthPolicy types + updateEndpoint client"
```

---

## Task 11: Frontend — service form dropdown + public_paths editor

**Files:**
- Modify: `apps-microservices/account-service-frontend/src/views/ApiCatalogFormView.vue`

- [ ] **Step 1: Read current form structure**

Read: `apps-microservices/account-service-frontend/src/views/ApiCatalogFormView.vue`. Identify where `form.description` / `form.owner` are bound.

- [ ] **Step 2: Add fields to the reactive form model**

In the `<script setup lang="ts">` block, extend the `form` ref:
```ts
const form = ref<CreateApiRequest & UpdateApiRequest>({
  // ... existing defaults ...
  authPolicy: 'public',
  publicPaths: [],
})
```

Add import for `AuthPolicy`:
```ts
import type { AuthPolicy, CreateApiRequest, UpdateApiRequest } from '@/types/apiCatalog'
```

On edit-mode load (the existing `onMounted` / `watchEffect` that fetches the service), populate the new fields:
```ts
form.value.authPolicy = svc.authPolicy ?? 'public'
form.value.publicPaths = svc.publicPaths ?? []
```

- [ ] **Step 3: Add the UI** — in the `<template>` block, after the description field, insert:

```vue
<div class="form-group">
  <label for="authPolicy">Auth policy</label>
  <select id="authPolicy" v-model="form.authPolicy" class="form-input">
    <option value="public">Public (no auth)</option>
    <option value="bearer">Bearer (JWT required)</option>
    <option value="admin-key">Admin key (X-Admin-Key)</option>
  </select>
</div>

<div class="form-group">
  <label for="publicPaths">Public paths (bypass auth — exact match, must start with /)</label>
  <div class="flex flex-wrap gap-2 mb-2">
    <span
      v-for="(p, i) in form.publicPaths"
      :key="i"
      class="inline-flex items-center px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded text-sm"
    >
      {{ p }}
      <button type="button" class="ml-1" @click="removePath(i)">×</button>
    </span>
  </div>
  <div class="flex gap-2">
    <input
      v-model="newPath"
      class="form-input flex-1"
      placeholder="/health"
      @keydown.enter.prevent="addPath"
    />
    <button type="button" class="btn btn-secondary" @click="addPath">Add</button>
  </div>
</div>
```

Add to `<script setup>`:
```ts
const newPath = ref('')
function addPath() {
  const v = newPath.value.trim().replace(/\/+$/, '')
  if (v && v.startsWith('/') && !v.match(/[*?]/) && !form.value.publicPaths?.includes(v)) {
    form.value.publicPaths = [...(form.value.publicPaths ?? []), v]
  }
  newPath.value = ''
}
function removePath(i: number) {
  form.value.publicPaths = (form.value.publicPaths ?? []).filter((_, idx) => idx !== i)
}
```

- [ ] **Step 4: Build the SPA**

Run: `cd apps-microservices/account-service-frontend && npm run build`
Expected: no TypeScript errors. (If the project enforces vue-tsc, run `npx vue-tsc --noEmit` too.)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-frontend/src/views/ApiCatalogFormView.vue
git commit -m "feat(account-service-frontend): auth policy dropdown + public_paths editor on service form"
```

---

## Task 12: Frontend — endpoint table inline policy select

**Files:**
- Modify: `apps-microservices/account-service-frontend/src/components/api-catalog/EndpointTable.vue`

- [ ] **Step 1: Read current table** — locate the column row.

- [ ] **Step 2: Add a Policy column**

In the `<script setup lang="ts">`:
```ts
import { ref } from 'vue'
import type { ApiCatalogEndpoint, AuthPolicy } from '@/types/apiCatalog'
import { updateEndpoint } from '@/api/apiCatalog'

const props = defineProps<{ serviceId: string; endpoints: ApiCatalogEndpoint[] }>()
const emit = defineEmits<{ (e: 'updated', endpoint: ApiCatalogEndpoint): void }>()

const saving = ref<Record<string, boolean>>({})

async function onPolicyChange(ep: ApiCatalogEndpoint, value: string) {
  saving.value[ep.id] = true
  const prev = ep.authPolicy
  const payload = { authPolicy: value === '' ? null : (value as AuthPolicy) }
  try {
    const next = await updateEndpoint(props.serviceId, ep.id, payload)
    emit('updated', next)
  } catch (err) {
    // revert
    ep.authPolicy = prev
    console.error('updateEndpoint failed:', err)
    alert('Failed to update endpoint policy: ' + (err as Error).message)
  } finally {
    saving.value[ep.id] = false
  }
}
```

In the `<template>` add a column. Inside the existing `<tr v-for="ep in endpoints">` row, add a `<td>`:

```vue
<td>
  <select
    :value="ep.authPolicy ?? ''"
    :disabled="saving[ep.id]"
    @change="onPolicyChange(ep, ($event.target as HTMLSelectElement).value)"
  >
    <option value="">(inherit)</option>
    <option value="public">public</option>
    <option value="bearer">bearer</option>
    <option value="admin-key">admin-key</option>
  </select>
</td>
```

And add a `<th>Policy</th>` to the header row.

- [ ] **Step 3: Ensure parent passes serviceId**

In `ApiCatalogDetailView.vue`, update the EndpointTable invocation:
```vue
<EndpointTable
  :service-id="service.id"
  :endpoints="endpoints"
  @updated="onEndpointUpdated"
/>
```

Add a handler that mutates the local endpoint list in-place so the table re-renders without refetch:
```ts
function onEndpointUpdated(next: ApiCatalogEndpoint) {
  const i = endpoints.value.findIndex((e) => e.id === next.id)
  if (i >= 0) endpoints.value[i] = next
}
```

- [ ] **Step 4: Build**

Run: `cd apps-microservices/account-service-frontend && npm run build`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/account-service-frontend/src/components/api-catalog/EndpointTable.vue \
        apps-microservices/account-service-frontend/src/views/ApiCatalogDetailView.vue
git commit -m "feat(account-service-frontend): inline auth policy select per endpoint"
```

---

## Task 13: Gateway — policy_snapshot package + tests

**Files:**
- Create: `apps-microservices/api-gateway-go/internal/auth/policy_snapshot.go`
- Create: `apps-microservices/api-gateway-go/internal/auth/policy_snapshot_test.go`

- [ ] **Step 1: Write failing test** — create `policy_snapshot_test.go`:

```go
package auth

import (
	"net/http"
	"testing"
)

func TestPolicyFor_UnknownService_FailOpen(t *testing.T) {
	snap := AuthSnapshot{}
	if got := snap.PolicyFor("ghost-service", http.MethodGet, "/x"); got != PolicyPublic {
		t.Fatalf("got=%v; want PolicyPublic", got)
	}
}

func TestPolicyFor_KnownService_DefaultBearer(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{Default: PolicyBearer},
	}
	if got := snap.PolicyFor("foo-service", "GET", "/x"); got != PolicyBearer {
		t.Fatalf("got=%v; want PolicyBearer", got)
	}
}

func TestPolicyFor_PublicPathBypass(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{
			Default:     PolicyBearer,
			PublicPaths: map[string]struct{}{"/healthz": {}},
		},
	}
	if got := snap.PolicyFor("foo-service", "GET", "/healthz"); got != PolicyPublic {
		t.Fatalf("got=%v; want PolicyPublic", got)
	}
}

func TestPolicyFor_EndpointOverrideWinsOverPublicPaths(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{
			Default:      PolicyPublic,
			PublicPaths:  map[string]struct{}{"/admin/burn": {}},
			EndpointAuth: map[string]AuthPolicy{"POST /admin/burn": PolicyAdminKey},
		},
	}
	if got := snap.PolicyFor("foo-service", "POST", "/admin/burn"); got != PolicyAdminKey {
		t.Fatalf("got=%v; want PolicyAdminKey (override wins over public_paths)", got)
	}
}

func TestPolicyFor_PathNormalization(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{
			Default:     PolicyBearer,
			PublicPaths: map[string]struct{}{"/dlq/queues": {}},
		},
	}
	// Verifier should normalize the inbound request path before lookup.
	cases := []string{"dlq/queues", "/dlq/queues", "dlq/queues/", "/dlq/queues/"}
	for _, p := range cases {
		if got := snap.PolicyFor("foo-service", "GET", p); got != PolicyPublic {
			t.Fatalf("path=%q got=%v; want PolicyPublic", p, got)
		}
	}
}
```

- [ ] **Step 2: Run — verify failure**

Run: `cd apps-microservices/api-gateway-go && go test ./internal/auth/ -run "PolicyFor_" -v`
Expected: FAIL — undefined types.

- [ ] **Step 3: Implement** — create `policy_snapshot.go`:

```go
package auth

import "strings"

// AuthPolicy enumerates the auth modes a service or endpoint may require.
// Mirrors api_catalog.AuthPolicy (proto). The numeric values are independent —
// translation lives in the catalog refresher.
type AuthPolicy int

const (
	PolicyPublic AuthPolicy = iota
	PolicyBearer
	PolicyAdminKey
)

// ServicePolicy carries the resolved auth state for one service.
type ServicePolicy struct {
	Default      AuthPolicy
	PublicPaths  map[string]struct{} // canonical: leading "/", no trailing "/"
	EndpointAuth map[string]AuthPolicy
}

// AuthSnapshot is the gateway-side view of the catalog's auth state.
// Key is the service name *including* the "-service" suffix.
type AuthSnapshot map[string]ServicePolicy

// canonicalPath turns gin's raw *path param into the storage form used by
// catalog (PublicPaths) and the EndpointAuth keys: "/foo" not "foo" or "foo/".
func canonicalPath(raw string) string {
	p := "/" + strings.Trim(raw, "/")
	return p
}

// PolicyFor resolves the effective auth policy for a single proxied request.
// Decision order: endpoint override → public_paths bypass → service default → PolicyPublic.
func (s AuthSnapshot) PolicyFor(service, method, path string) AuthPolicy {
	sp, ok := s[service]
	if !ok {
		return PolicyPublic
	}
	cp := canonicalPath(path)
	if p, ok := sp.EndpointAuth[method+" "+cp]; ok {
		return p
	}
	if _, ok := sp.PublicPaths[cp]; ok {
		return PolicyPublic
	}
	return sp.Default
}
```

- [ ] **Step 4: Re-run**

Run: `go test ./internal/auth/ -run "PolicyFor_" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/auth/policy_snapshot.go \
        apps-microservices/api-gateway-go/internal/auth/policy_snapshot_test.go
git commit -m "feat(api-gateway-go): auth.AuthSnapshot decision tree"
```

---

## Task 14: Gateway — extend catalog.Refresher with AuthSnapshot

**Files:**
- Modify: `apps-microservices/api-gateway-go/internal/catalog/refresher.go`
- Modify: `apps-microservices/api-gateway-go/internal/catalog/client.go`
- Modify: `apps-microservices/api-gateway-go/internal/catalog/refresher_test.go`

- [ ] **Step 1: Write failing test** — append to `refresher_test.go`:

```go
func TestRefresher_BuildsAuthSnapshot_WithEndpointOverridesHint(t *testing.T) {
	fake := &fakeCatalog{
		services: []*pb.Service{
			{Id: "a", Name: "a-service", BaseUrl: "http://a", Status: pb.Status_ACTIVE,
				AuthPolicy: pb.AuthPolicy_BEARER, PublicPaths: []string{"/healthz"}, HasEndpointOverrides: true},
			{Id: "b", Name: "b-service", BaseUrl: "http://b", Status: pb.Status_ACTIVE,
				AuthPolicy: pb.AuthPolicy_PUBLIC},
		},
		endpoints: map[string][]*pb.Endpoint{
			"a": {
				{Id: "ep1", ServiceId: "a", Method: "POST", Path: "/admin", AuthPolicy: enumPtr(pb.AuthPolicy_ADMIN_KEY)},
			},
		},
	}
	r := NewRefresher(fake, time.Hour, nil)
	routes, src := r.Bootstrap(context.Background(), 5*time.Second)
	if src != "catalog" {
		t.Fatalf("source=%q; want catalog", src)
	}
	if _, ok := routes["/a-service"]; !ok {
		t.Fatalf("routes missing a-service")
	}
	_, auth, _ := r.Snapshot()
	a, ok := auth["a-service"]
	if !ok {
		t.Fatal("auth snapshot missing a-service")
	}
	if a.Default != auth_pkg.PolicyBearer {
		t.Fatalf("default=%v; want PolicyBearer", a.Default)
	}
	if _, ok := a.PublicPaths["/healthz"]; !ok {
		t.Fatal("public path /healthz missing")
	}
	if a.EndpointAuth["POST /admin"] != auth_pkg.PolicyAdminKey {
		t.Fatalf("endpoint override = %v; want PolicyAdminKey", a.EndpointAuth["POST /admin"])
	}
	if fake.listEndpointsCalls != 1 {
		t.Fatalf("ListEndpoints called %d times; want 1 (b-service has no overrides hint)", fake.listEndpointsCalls)
	}
}

// helper for proto enum pointers
func enumPtr(p pb.AuthPolicy) *pb.AuthPolicy { return &p }
```

Add (or extend if present) the fake at the top of `refresher_test.go`:
```go
type fakeCatalog struct {
	services           []*pb.Service
	endpoints          map[string][]*pb.Endpoint
	listEndpointsCalls int
}

func (f *fakeCatalog) ListServices(ctx context.Context, in *pb.ListServicesRequest, _ ...grpc.CallOption) (*pb.ListServicesResponse, error) {
	return &pb.ListServicesResponse{Items: f.services, Total: int64(len(f.services))}, nil
}
func (f *fakeCatalog) ListEndpoints(ctx context.Context, in *pb.ListEndpointsRequest, _ ...grpc.CallOption) (*pb.ListEndpointsResponse, error) {
	f.listEndpointsCalls++
	return &pb.ListEndpointsResponse{Items: f.endpoints[in.GetServiceId()]}, nil
}
```

Add imports as needed:
```go
auth_pkg "api-gateway-go/internal/auth"
"google.golang.org/grpc"
pb "api-gateway-go/internal/genproto/api_catalog"
```

- [ ] **Step 2: Update `Client` to accept the fake interface**

In `client.go`, extract a minimal interface satisfied by the generated client and `fakeCatalog`:

```go
// catalogRPC is the surface of pb.ApiCatalogClient consumed by Client.
// Defined so tests can substitute an in-process fake without spinning bufconn.
type catalogRPC interface {
	ListServices(ctx context.Context, in *pb.ListServicesRequest, opts ...grpc.CallOption) (*pb.ListServicesResponse, error)
	ListEndpoints(ctx context.Context, in *pb.ListEndpointsRequest, opts ...grpc.CallOption) (*pb.ListEndpointsResponse, error)
}

// Client wraps the generated gRPC ApiCatalog client.
type Client struct{ cli catalogRPC }

// NewClient constructs a Client from an existing gRPC connection.
func NewClient(conn *grpc.ClientConn) *Client { return &Client{cli: pb.NewApiCatalogClient(conn)} }
```

Add `BuildAuthSnapshot` alongside `BuildMap`:
```go
import (
	"context"
	auth_pkg "api-gateway-go/internal/auth"
	pb "api-gateway-go/internal/genproto/api_catalog"
)

// authPolicyFromProto translates the proto enum to the gateway-side AuthPolicy.
// UNSPECIFIED coerces to PolicyPublic (spec §8: fail-open default).
func authPolicyFromProto(p pb.AuthPolicy) auth_pkg.AuthPolicy {
	switch p {
	case pb.AuthPolicy_BEARER:
		return auth_pkg.PolicyBearer
	case pb.AuthPolicy_ADMIN_KEY:
		return auth_pkg.PolicyAdminKey
	}
	return auth_pkg.PolicyPublic
}

// BuildMapAndAuthSnapshot returns routes + AuthSnapshot in a single pass over
// ListServices. ListEndpoints is called only for services with
// HasEndpointOverrides=true, bounding the fan-out.
func (c *Client) BuildMapAndAuthSnapshot(ctx context.Context) (map[string]string, auth_pkg.AuthSnapshot, error) {
	resp, err := c.cli.ListServices(ctx, &pb.ListServicesRequest{Limit: 1000})
	if err != nil {
		return nil, nil, err
	}
	routes := make(map[string]string, len(resp.GetItems()))
	snap := make(auth_pkg.AuthSnapshot, len(resp.GetItems()))
	for _, s := range resp.GetItems() {
		if s.GetStatus() != pb.Status_ACTIVE {
			continue
		}
		routes["/"+s.GetName()] = s.GetBaseUrl()
		sp := auth_pkg.ServicePolicy{
			Default:     authPolicyFromProto(s.GetAuthPolicy()),
			PublicPaths: map[string]struct{}{},
		}
		for _, p := range s.GetPublicPaths() {
			sp.PublicPaths[p] = struct{}{}
		}
		if s.GetHasEndpointOverrides() {
			epResp, err := c.cli.ListEndpoints(ctx, &pb.ListEndpointsRequest{ServiceId: s.GetId()})
			if err == nil {
				ea := make(map[string]auth_pkg.AuthPolicy, len(epResp.GetItems()))
				for _, e := range epResp.GetItems() {
					if e.AuthPolicy == nil {
						continue
					}
					key := e.GetMethod() + " " + e.GetPath()
					ea[key] = authPolicyFromProto(*e.AuthPolicy)
				}
				sp.EndpointAuth = ea
			}
		}
		snap[s.GetName()] = sp
	}
	return routes, snap, nil
}

// BuildMap kept for back-compat with any callers still using it.
func (c *Client) BuildMap(ctx context.Context) (map[string]string, error) {
	m, _, err := c.BuildMapAndAuthSnapshot(ctx)
	return m, err
}
```

- [ ] **Step 3: Update Refresher** — replace `refresher.go`:

```go
package catalog

import (
	"context"
	"log"
	"sync"
	"time"

	auth_pkg "api-gateway-go/internal/auth"
)

type Refresher struct {
	cli      *Client
	interval time.Duration
	fallback map[string]string
	mu       sync.RWMutex
	routes   map[string]string
	auth     auth_pkg.AuthSnapshot
	source   string
}

func NewRefresher(cli *Client, interval time.Duration, fallback map[string]string) *Refresher {
	return &Refresher{cli: cli, interval: interval, fallback: fallback}
}

func (r *Refresher) Bootstrap(ctx context.Context, dialTimeout time.Duration) (map[string]string, string) {
	bctx, cancel := context.WithTimeout(ctx, dialTimeout)
	defer cancel()
	routes, snap, err := r.cli.BuildMapAndAuthSnapshot(bctx)
	if err != nil || len(routes) == 0 {
		log.Printf("catalog bootstrap: using env fallback (err=%v len=%d)", err, len(routes))
		r.set(r.fallback, auth_pkg.AuthSnapshot{}, "env")
		return r.fallback, "env"
	}
	r.set(routes, snap, "catalog")
	return routes, "catalog"
}

func (r *Refresher) Run(ctx context.Context) {
	t := time.NewTicker(r.interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			rctx, cancel := context.WithTimeout(ctx, 5*time.Second)
			routes, snap, err := r.cli.BuildMapAndAuthSnapshot(rctx)
			cancel()
			if err != nil || len(routes) == 0 {
				log.Printf("catalog refresh failed; keeping last map (err=%v len=%d)", err, len(routes))
				continue
			}
			r.set(routes, snap, "catalog")
		}
	}
}

// Snapshot returns (routes, AuthSnapshot, source).
func (r *Refresher) Snapshot() (map[string]string, auth_pkg.AuthSnapshot, string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.routes, r.auth, r.source
}

func (r *Refresher) set(routes map[string]string, snap auth_pkg.AuthSnapshot, src string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.routes, r.auth, r.source = routes, snap, src
}
```

- [ ] **Step 4: Run tests**

Run: `cd apps-microservices/api-gateway-go && go test ./internal/catalog/ -v`
Expected: PASS. (Existing tests may need their `Snapshot()` callsites updated to the new 3-value return — fix any compile breakage by adding `_` for the AuthSnapshot return.)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/catalog/
git commit -m "feat(api-gateway-go): refresher builds AuthSnapshot alongside routes"
```

---

## Task 15: Gateway — verifier reads snapshot (remove TODO short-circuit)

**Files:**
- Modify: `apps-microservices/api-gateway-go/internal/auth/api_token.go`
- Modify: `apps-microservices/api-gateway-go/internal/auth/api_token_test.go`

- [ ] **Step 1: Write failing test** — append to `api_token_test.go`:

```go
func TestVerifier_PolicyPublic_AllowsWithoutBearer(t *testing.T) {
	v := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyPublic}}, "admin-key")
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request, _ = http.NewRequest("GET", "/foo-service/x", nil)
	c.Params = gin.Params{{Key: "service", Value: "foo-service"}, {Key: "path", Value: "/x"}}
	v.Middleware()(c)
	if c.IsAborted() {
		t.Fatalf("status=%d body=%s; want allowed", w.Code, w.Body.String())
	}
}

func TestVerifier_PolicyBearer_RequiresToken(t *testing.T) {
	v := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyBearer}}, "")
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request, _ = http.NewRequest("GET", "/foo-service/x", nil)
	c.Params = gin.Params{{Key: "service", Value: "foo-service"}, {Key: "path", Value: "/x"}}
	v.Middleware()(c)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d; want 401", w.Code)
	}
}

func TestVerifier_PolicyAdminKey_ChecksHeader(t *testing.T) {
	v := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyAdminKey}}, "k123")
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request, _ = http.NewRequest("GET", "/foo-service/x", nil)
	c.Request.Header.Set("X-Admin-Key", "k123")
	c.Params = gin.Params{{Key: "service", Value: "foo-service"}, {Key: "path", Value: "/x"}}
	v.Middleware()(c)
	if c.IsAborted() {
		t.Fatalf("expected pass; got status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestVerifier_PolicyAdminKey_Rejects_WrongHeader(t *testing.T) {
	v := newVerifier(t, AuthSnapshot{"foo-service": {Default: PolicyAdminKey}}, "k123")
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request, _ = http.NewRequest("GET", "/foo-service/x", nil)
	c.Request.Header.Set("X-Admin-Key", "wrong")
	c.Params = gin.Params{{Key: "service", Value: "foo-service"}, {Key: "path", Value: "/x"}}
	v.Middleware()(c)
	if w.Code != http.StatusForbidden {
		t.Fatalf("status=%d; want 403", w.Code)
	}
}

func TestVerifier_UnknownService_FailOpen(t *testing.T) {
	v := newVerifier(t, AuthSnapshot{}, "k123")
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request, _ = http.NewRequest("GET", "/ghost-service/x", nil)
	c.Params = gin.Params{{Key: "service", Value: "ghost-service"}, {Key: "path", Value: "/x"}}
	v.Middleware()(c)
	if c.IsAborted() {
		t.Fatalf("expected pass (fail-open); got status=%d", w.Code)
	}
}
```

Add helper (if not already present):
```go
func newVerifier(t *testing.T, snap AuthSnapshot, adminKey string) *APITokenVerifier {
	t.Helper()
	jwt := NewJWT("secret", "HS256", time.Minute)
	getSnap := func() AuthSnapshot { return snap }
	return NewAPITokenVerifier(jwt, nil, nil, getSnap, adminKey)
}
```

Add imports: `"net/http/httptest"`, `"github.com/gin-gonic/gin"`, `"time"`.

- [ ] **Step 2: Run — verify failure**

Run: `cd apps-microservices/api-gateway-go && go test ./internal/auth/ -run "Verifier_Policy|UnknownService_FailOpen" -v`
Expected: FAIL — `NewAPITokenVerifier` signature mismatch; TODO short-circuit makes everything pass without checks.

- [ ] **Step 3: Rewrite verifier** — replace `api_token.go`:

```go
package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	cachepkg "api-gateway-go/internal/cache"
	dbpkg "api-gateway-go/internal/db"
)

// APITokenVerifier validates auth on proxied requests per the catalog AuthSnapshot.
// Spec: docs/superpowers/specs/2026-05-28-apitokenverifier-catalog-driven-design.md
type APITokenVerifier struct {
	jwt      *JWT
	db       *gorm.DB
	cache    *cachepkg.Cache
	getSnap  func() AuthSnapshot
	adminKey string

	unknownMu  sync.Mutex
	unknownSeen map[string]time.Time // log-spam suppressor
}

func NewAPITokenVerifier(j *JWT, g *gorm.DB, c *cachepkg.Cache, getSnap func() AuthSnapshot, adminKey string) *APITokenVerifier {
	return &APITokenVerifier{
		jwt: j, db: g, cache: c, getSnap: getSnap, adminKey: adminKey,
		unknownSeen: map[string]time.Time{},
	}
}

func (v *APITokenVerifier) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		service := c.Param("service")
		path := c.Param("path")
		method := c.Request.Method

		snap := v.getSnap()
		if _, known := snap[service]; !known {
			v.logUnknown(service)
		}
		policy := snap.PolicyFor(service, method, path)

		switch policy {
		case PolicyPublic:
			c.Set("token_payload", gin.H{"sub": service, "is_excluded": true})
			c.Next()
			return
		case PolicyAdminKey:
			if v.adminKey == "" || c.GetHeader("X-Admin-Key") != v.adminKey {
				c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"detail": "Invalid or missing admin key."})
				return
			}
			c.Set("token_payload", gin.H{"sub": service, "is_admin": true})
			c.Next()
			return
		case PolicyBearer:
			// fall through to bearer flow
		}

		authHeader := c.GetHeader("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			abortAuth(c, "Access token manquant ou invalide.")
			return
		}
		raw := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))

		claims, err := v.jwt.VerifyAccessToken(raw)
		if err != nil {
			if errors.Is(err, ErrExpired) {
				abortAuth(c, "Access token has expired. Please refresh.")
			} else {
				abortAuth(c, "Invalid access token.")
			}
			return
		}

		ctx := c.Request.Context()
		var redisPayload map[string]any
		if v.cache != nil {
			found, _ := v.cache.GetJSON(ctx, "access_token:"+raw, &redisPayload)
			if found {
				c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
				c.Next()
				return
			}
		}

		if !v.dbAccessTokenActive(ctx, raw) {
			abortAuth(c, "Access token has been revoked or expired.")
			return
		}
		c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
		c.Next()
	}
}

func abortAuth(c *gin.Context, detail string) {
	c.Header("WWW-Authenticate", "Bearer")
	c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"detail": detail})
}

func (v *APITokenVerifier) dbAccessTokenActive(ctx context.Context, token string) bool {
	if v.db == nil {
		return false
	}
	now := time.Now().UTC()
	var access dbpkg.InfoAccessToken
	err := v.db.WithContext(ctx).
		Preload("RefreshToken").
		Where("token = ? AND est_actif = ? AND date_expiration >= ?", token, true, now).
		First(&access).Error
	if err != nil {
		return false
	}
	return access.RefreshToken.EstActif
}

// logUnknown emits at most one WARN per service per hour.
func (v *APITokenVerifier) logUnknown(service string) {
	v.unknownMu.Lock()
	defer v.unknownMu.Unlock()
	if last, ok := v.unknownSeen[service]; ok && time.Since(last) < time.Hour {
		return
	}
	v.unknownSeen[service] = time.Now()
	// Using standard log to match the rest of the package; access logs use a
	// different path. Keep this terse — one line per (service, hour).
	logUnknownService(service)
}
```

Add a tiny helper in a separate file (or directly above) so tests can override the logger if needed:
```go
// in api_token.go, near the bottom
import "log"
func logUnknownService(service string) {
	log.Printf("[verifier] WARN unknown service=%q not in AuthSnapshot; failing open", service)
}
```

- [ ] **Step 4: Re-run unit tests**

Run: `go test ./internal/auth/ -v`
Expected: all new + existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/auth/api_token.go \
        apps-microservices/api-gateway-go/internal/auth/api_token_test.go
git commit -m "feat(api-gateway-go): drive APITokenVerifier from AuthSnapshot, remove TODO bypass"
```

---

## Task 16: Gateway — remove BuildExcludedRoutes + wire snapshot in main

**Files:**
- Modify: `apps-microservices/api-gateway-go/internal/config/service_map.go`
- Modify: `apps-microservices/api-gateway-go/internal/config/service_map_test.go`
- Modify: `apps-microservices/api-gateway-go/cmd/gateway/main.go`

- [ ] **Step 1: Delete `BuildExcludedRoutes`** — in `service_map.go`, remove the entire `BuildExcludedRoutes` function. The remaining helpers (`BuildServiceMap`, `BuildDownstreamTimeouts`, `ExcludedServices`) stay untouched.

- [ ] **Step 2: Drop the test** — in `service_map_test.go`, remove any `TestBuildExcludedRoutes*` test functions. If the test file only contained that test, leave the package declaration + one trivial test or remove the file.

- [ ] **Step 3: Wire snapshot getter in main**

In `main.go`, edit the `verifier := auth.NewAPITokenVerifier(...)` line. First add a getter that prefers the live refresher snapshot, falling back to an empty snapshot (which routes every service to PolicyPublic):

```go
getAuthSnapshot := func() auth.AuthSnapshot { return auth.AuthSnapshot{} }
// ... inside the existing `if cfg.UseCatalog` block, after `refresher.Bootstrap(...)`:
getAuthSnapshot = func() auth.AuthSnapshot {
	_, snap, _ := refresher.Snapshot()
	if snap == nil {
		return auth.AuthSnapshot{}
	}
	return snap
}
```

Update the existing `getServices` block accordingly — its `Snapshot()` call now returns three values:
```go
getServices = func() map[string]string {
	cur, _, _ := refresher.Snapshot()
	if cur == nil {
		return serviceMap
	}
	return cur
}
```

Replace the verifier construction:
```go
verifier := auth.NewAPITokenVerifier(jwtSvc, gdb, cache, getAuthSnapshot, cfg.GatewayAdminKey)
```

Delete the now-dead `config.BuildExcludedRoutes` import (the call is removed).

- [ ] **Step 4: Build the whole gateway**

Run: `cd apps-microservices/api-gateway-go && go build ./...`
Expected: clean.

Run: `go test ./...`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-gateway-go/internal/config/service_map.go \
        apps-microservices/api-gateway-go/internal/config/service_map_test.go \
        apps-microservices/api-gateway-go/cmd/gateway/main.go
git commit -m "feat(api-gateway-go): wire AuthSnapshot into verifier; drop BuildExcludedRoutes"
```

---

## Task 17: Manual smoke + service CLAUDE.md update

**Files:**
- Modify: `apps-microservices/api-gateway-go/CLAUDE.md`
- Modify: `apps-microservices/api-catalog-service/CLAUDE.md`

- [ ] **Step 1: Update gateway CLAUDE.md** — replace the "Conventions" section's auth bullet and the "Per-Service Downstream Timeouts" preamble with a new section right after "Conventions":

```markdown
## Auth Policy (catalog-driven)

The verifier reads per-service `AuthPolicy` and `public_paths` from the catalog
`Refresher` snapshot — there is no longer any hardcoded auth state in the
gateway. Decision order per request:

1. Endpoint override (`Endpoint.auth_policy` in catalog) wins.
2. Else service `public_paths` exact match → `PUBLIC`.
3. Else service `auth_policy` default.
4. Unknown service → `PUBLIC` (fail-open; logged once per hour).

Edit policies in account-service-frontend → catalog updates → ≤60 s for the
gateway snapshot to pick up the change.
```

- [ ] **Step 2: Update api-catalog-service CLAUDE.md** — add to "What This Provides":

```markdown
- Per-service `AuthPolicy` (public/bearer/admin-key) + `public_paths` exact-match bypass list.
- Per-endpoint `auth_policy` override.
- `has_endpoint_overrides` hint on `Service` (computed) — lets clients skip `ListEndpoints` when no overrides exist.
```

- [ ] **Step 3: Manual smoke checklist**

After deploying the full chain in dev:

```
1. GET /graphdlq-service/dlq/queues  (no Authorization)        → 200 (public_paths bypass)
2. GET /graphdlq-service/other                                  → 200 (default PUBLIC at cutover)
3. In admin UI, set graphdlq-service.auth_policy = BEARER. Wait ≤60s.
4. GET /graphdlq-service/dlq/queues                             → 200 (public_paths still wins)
5. GET /graphdlq-service/other                                  → 401
6. Set endpoint override on /graphdlq-service/other = ADMIN_KEY. Wait ≤60s.
7. GET /graphdlq-service/other (X-Admin-Key: $GATEWAY_ADMIN_KEY) → 200
8. GET /graphdlq-service/other (wrong key)                       → 403
```

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-gateway-go/CLAUDE.md \
        apps-microservices/api-catalog-service/CLAUDE.md
git commit -m "docs: document catalog-driven AuthPolicy + public_paths in service CLAUDE.md"
```

---

## Self-Review (run after writing — already applied below)

- **Spec coverage** — every section §6.1–§6.5 mapped: §6.1 → Task 1; §6.2 → Tasks 3-7; §6.3 → Tasks 8-9; §6.4 → Tasks 10-12; §6.5 → Tasks 13-16. Error handling §8 covered by Verifier tests (Task 15), handler validation (Task 8), refresher fail-open (Task 14). Testing strategy §9 mirrored in TDD steps.
- **Placeholder scan** — none.
- **Type consistency** — `AuthSnapshot`, `ServicePolicy`, `PolicyPublic|Bearer|AdminKey` used identically across Tasks 13-16. `pb.AuthPolicy_{PUBLIC,BEARER,ADMIN_KEY}` referenced consistently. JSON keys `authPolicy` / `publicPaths` / `hasEndpointOverrides` aligned between Go server (Task 8), TS types (Task 10), Vue forms (Tasks 11-12).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-28-apitokenverifier-catalog-driven.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
