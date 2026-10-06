package tools

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

const testAdminKey = "test-admin-key-0123456789"

// fakeRegistry records every call, the authorization metadata it carried, and the last request per RPC.
type fakeRegistry struct {
	mu          sync.Mutex
	calls       []string
	auth        map[string]string
	units       map[string]*unitregistrypb.UnitResponse     // by token
	types       map[string]*unitregistrypb.UnitTypeResponse // by code
	err         error
	lastReg     *unitregistrypb.RegisterUnitRequest
	lastUpdate  *unitregistrypb.UpdateUnitRequest
	lastDelete  *unitregistrypb.DeleteUnitRequest
	lastGet     *unitregistrypb.GetUnitRequest
	lastCreateT *unitregistrypb.CreateUnitTypeRequest
	lastUpdateT *unitregistrypb.UpdateUnitTypeRequest
	lastDeactT  *unitregistrypb.DeactivateUnitTypeRequest
	lastGetT    *unitregistrypb.GetUnitTypeRequest
	lastSetDims *unitregistrypb.SetDimensionTypesRequest
}

func newFakeRegistry() *fakeRegistry {
	return &fakeRegistry{
		auth: map[string]string{},
		units: map[string]*unitregistrypb.UnitResponse{
			"kg": {Id: "u-kg", Spec: &unitregistrypb.UnitSpec{Token: "kg", Dimension: "mass"}, Status: "ACTIVE", Source: "seed", Types: []string{"CAPACITY"}},
		},
		types: map[string]*unitregistrypb.UnitTypeResponse{
			"CAPACITY": {Id: "t-cap", Spec: &unitregistrypb.UnitTypeSpec{Code: "CAPACITY", Label: "Capacité"}, IsActive: true},
		},
	}
}

func (f *fakeRegistry) record(ctx context.Context, method string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, method)
	if md, ok := metadata.FromOutgoingContext(ctx); ok {
		if v := md.Get("authorization"); len(v) > 0 {
			f.auth[method] = v[0]
		}
	}
	if _, ok := ctx.Deadline(); !ok {
		return errors.New("call has no deadline")
	}
	return f.err
}

func (f *fakeRegistry) RegisterUnit(ctx context.Context, in *unitregistrypb.RegisterUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitResponse, error) {
	if err := f.record(ctx, "RegisterUnit"); err != nil {
		return nil, err
	}
	f.lastReg = in
	return &unitregistrypb.UnitResponse{Id: "u-" + in.GetSpec().GetToken(), Spec: in.GetSpec(), Status: "ACTIVE", Source: "manual", RegistryVersion: 2, CreatedBy: in.GetCreatedBy()}, nil
}

func (f *fakeRegistry) GetUnit(ctx context.Context, in *unitregistrypb.GetUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitResponse, error) {
	if err := f.record(ctx, "GetUnit"); err != nil {
		return nil, err
	}
	f.lastGet = in
	for _, u := range f.units {
		if (in.GetId() != "" && u.GetId() == in.GetId()) || (in.GetToken() != "" && u.GetSpec().GetToken() == in.GetToken()) {
			return u, nil
		}
	}
	return nil, status.Error(codes.NotFound, "unit '"+in.GetToken()+in.GetId()+"' not found")
}

func (f *fakeRegistry) ListUnits(context.Context, *unitregistrypb.ListUnitsRequest, ...grpc.CallOption) (*unitregistrypb.ListUnitsResponse, error) {
	return nil, errors.New("ListUnits is not used by the tools")
}

func (f *fakeRegistry) UpdateUnit(ctx context.Context, in *unitregistrypb.UpdateUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitResponse, error) {
	if err := f.record(ctx, "UpdateUnit"); err != nil {
		return nil, err
	}
	f.lastUpdate = in
	return &unitregistrypb.UnitResponse{Id: in.GetId(), Spec: in.GetSpec(), Status: "ACTIVE", Source: "manual", RegistryVersion: 3}, nil
}

func (f *fakeRegistry) DeleteUnit(ctx context.Context, in *unitregistrypb.DeleteUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.DeleteUnitResponse, error) {
	if err := f.record(ctx, "DeleteUnit"); err != nil {
		return nil, err
	}
	f.lastDelete = in
	return &unitregistrypb.DeleteUnitResponse{Success: true}, nil
}

func (f *fakeRegistry) GetRegistryStatus(context.Context, *unitregistrypb.GetRegistryStatusRequest, ...grpc.CallOption) (*unitregistrypb.RegistryStatus, error) {
	return nil, errors.New("GetRegistryStatus is not used by the tools")
}

func (f *fakeRegistry) ValidateUnit(context.Context, *unitregistrypb.ValidateUnitRequest, ...grpc.CallOption) (*unitregistrypb.ValidationResult, error) {
	return nil, errors.New("ValidateUnit is not used by the tools")
}

func (f *fakeRegistry) CreateUnitType(ctx context.Context, in *unitregistrypb.CreateUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "CreateUnitType"); err != nil {
		return nil, err
	}
	f.lastCreateT = in
	return &unitregistrypb.UnitTypeResponse{Id: "t-" + in.GetSpec().GetCode(), Spec: in.GetSpec(), IsActive: true}, nil
}

func (f *fakeRegistry) UpdateUnitType(ctx context.Context, in *unitregistrypb.UpdateUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "UpdateUnitType"); err != nil {
		return nil, err
	}
	f.lastUpdateT = in
	return &unitregistrypb.UnitTypeResponse{Id: in.GetId(), Spec: in.GetSpec(), IsActive: true}, nil
}

func (f *fakeRegistry) DeactivateUnitType(ctx context.Context, in *unitregistrypb.DeactivateUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "DeactivateUnitType"); err != nil {
		return nil, err
	}
	f.lastDeactT = in
	return &unitregistrypb.UnitTypeResponse{Id: in.GetId(), Spec: &unitregistrypb.UnitTypeSpec{Code: "CAPACITY"}, IsActive: false}, nil
}

func (f *fakeRegistry) GetUnitType(ctx context.Context, in *unitregistrypb.GetUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "GetUnitType"); err != nil {
		return nil, err
	}
	f.lastGetT = in
	for _, t := range f.types {
		if (in.GetId() != "" && t.GetId() == in.GetId()) || (in.GetCode() != "" && t.GetSpec().GetCode() == in.GetCode()) {
			return t, nil
		}
	}
	return nil, status.Error(codes.NotFound, "type "+in.GetCode()+in.GetId()+" not found")
}

func (f *fakeRegistry) ListUnitTypes(ctx context.Context, _ *unitregistrypb.ListUnitTypesRequest, _ ...grpc.CallOption) (*unitregistrypb.ListUnitTypesResponse, error) {
	if err := f.record(ctx, "ListUnitTypes"); err != nil {
		return nil, err
	}
	out := &unitregistrypb.ListUnitTypesResponse{}
	for _, t := range f.types {
		out.Types = append(out.Types, t)
	}
	return out, nil
}

func (f *fakeRegistry) SetDimensionTypes(ctx context.Context, in *unitregistrypb.SetDimensionTypesRequest, _ ...grpc.CallOption) (*unitregistrypb.DimensionTypesResponse, error) {
	if err := f.record(ctx, "SetDimensionTypes"); err != nil {
		return nil, err
	}
	f.lastSetDims = in
	return &unitregistrypb.DimensionTypesResponse{Dimension: in.GetDimension(), TypeCodes: in.GetTypeCodes()}, nil
}

func callRegistry(t *testing.T, fake *fakeRegistry, tool string, args map[string]any) *mcp.CallToolResult {
	t.Helper()
	raw, err := json.Marshal(args)
	if err != nil {
		t.Fatalf("marshal args: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal args: %v", err)
	}
	r := NewRegistry(&Clients{Normalization: &fakeNormalization{}, Units: fake, UnitsAdminKey: testAdminKey, Actor: "mcp:test"})
	return r.CallTool(context.Background(), &mcp.CallToolParams{Name: tool, Arguments: decoded})
}

func sampleArgs() map[string]any {
	return map[string]any{"label": "Poids", "value": 2, "expected_canonical_value": 50, "expected_canonical_unit": "kilogram"}
}

func TestCreateUnitForwardsEverythingWithTheBearer(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "create_unit", map[string]any{
		"token": "sac_ciment", "dimension": "mass", "pint_definition": "sac_ciment = 25 * kilogram",
		"aliases": []any{"sacs"}, "sample": sampleArgs(),
	})
	var out unitView
	decode(t, res, &out)
	if out.ID != "u-sac_ciment" || out.RegistryVersion != 2 || len(out.Types) != 0 {
		t.Fatalf("unexpected view: %+v", out)
	}
	spec := fake.lastReg.GetSpec()
	if spec.GetDimension() != "mass" || spec.GetAliases()[0] != "sacs" || fake.lastReg.GetCreatedBy() != "mcp:test" {
		t.Fatalf("unexpected request: %+v", fake.lastReg)
	}
	s := spec.GetRegressionSample()
	if s.GetValue() != "2" || s.GetExpectedCanonicalValue() != 50 || s.GetDataType() != "numeric" {
		t.Fatalf("unexpected sample: %+v", s)
	}
	if fake.auth["RegisterUnit"] != "Bearer "+testAdminKey {
		t.Fatalf("missing bearer: %q", fake.auth["RegisterUnit"])
	}
}

func TestCreateUnitAcceptsNumericStringsInSample(t *testing.T) {
	fake := newFakeRegistry()
	sample := map[string]any{"label": "Poids", "value": "2", "expected_canonical_value": "50", "expected_canonical_unit": "kilogram"}
	res := callRegistry(t, fake, "create_unit", map[string]any{"token": "sac", "dimension": "mass", "sample": sample})
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content[0].Text)
	}
	if fake.lastReg.GetSpec().GetRegressionSample().GetExpectedCanonicalValue() != 50 {
		t.Fatalf("string number not parsed")
	}
}

func TestCreateUnitValidation(t *testing.T) {
	cases := []struct {
		name string
		args map[string]any
		want string
	}{
		{"no sample", map[string]any{"token": "sac", "dimension": "mass"}, "'sample' parameter is required"},
		{"no token", map[string]any{"dimension": "mass", "sample": sampleArgs()}, "'token'"},
		{"no dimension", map[string]any{"token": "sac", "sample": sampleArgs()}, "'dimension'"},
		{"bad aliases", map[string]any{"token": "sac", "dimension": "mass", "aliases": "sacs", "sample": sampleArgs()}, "'aliases' must be an array"},
		{"range without max", map[string]any{"token": "sac", "dimension": "mass", "sample": map[string]any{
			"label": "Poids", "value": 1, "data_type": "numeric_range", "expected_canonical_value": 25, "expected_canonical_unit": "kilogram"}}, "value_max"},
		{"bad data_type", map[string]any{"token": "sac", "dimension": "mass", "sample": map[string]any{
			"label": "Poids", "value": 1, "data_type": "text", "expected_canonical_value": 25, "expected_canonical_unit": "kilogram"}}, "data_type"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			fake := newFakeRegistry()
			wantError(t, callRegistry(t, fake, "create_unit", tc.args), tc.want)
			if len(fake.calls) != 0 {
				t.Fatalf("backend called despite invalid input: %v", fake.calls)
			}
		})
	}
}

func TestServerValidationErrorsPassThrough(t *testing.T) {
	fake := newFakeRegistry()
	fake.err = status.Error(codes.InvalidArgument, "G1: pint cannot evaluate 'x = 3 * nope'")
	wantError(t, callRegistry(t, fake, "create_unit", map[string]any{"token": "x", "dimension": "mass", "sample": sampleArgs()}), "G1: pint cannot evaluate")
}

func TestUnauthenticatedAndUnavailableErrors(t *testing.T) {
	fake := newFakeRegistry()
	fake.err = status.Error(codes.Unauthenticated, "missing or invalid admin bearer")
	wantError(t, callRegistry(t, fake, "deactivate_unit", map[string]any{"id": "u-kg"}), "UNITS_ADMIN_KEY")
	fake.err = status.Error(codes.Unavailable, "connection refused")
	wantError(t, callRegistry(t, fake, "get_unit", map[string]any{"id": "u-kg"}), "unit registry unavailable")
}

func TestUpdateUnitByTokenSendsOnlyTheGivenFields(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "update_unit", map[string]any{"token": "kg", "aliases": []any{}})
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content[0].Text)
	}
	if fake.lastGet.GetToken() != "kg" || fake.auth["GetUnit"] != "" {
		t.Fatalf("token lookup must be an unauthenticated read: %+v auth=%q", fake.lastGet, fake.auth["GetUnit"])
	}
	if fake.lastUpdate.GetId() != "u-kg" || len(fake.lastUpdate.GetSpec().GetAliases()) != 0 {
		t.Fatalf("unexpected update: %+v", fake.lastUpdate)
	}
	if paths := fake.lastUpdate.GetUpdateMask().GetPaths(); len(paths) != 1 || paths[0] != "aliases" {
		t.Fatalf("mask = %v", paths)
	}
	if fake.auth["UpdateUnit"] != "Bearer "+testAdminKey {
		t.Fatalf("missing bearer on UpdateUnit")
	}
}

func TestUpdateUnitSampleMapsToRegressionSamplePath(t *testing.T) {
	fake := newFakeRegistry()
	callRegistry(t, fake, "update_unit", map[string]any{"id": "u-kg", "dimension": "mass", "sample": sampleArgs()})
	paths := fake.lastUpdate.GetUpdateMask().GetPaths()
	if len(paths) != 2 || paths[0] != "dimension" || paths[1] != "regression_sample" {
		t.Fatalf("mask = %v", paths)
	}
}

func TestUpdateUnitValidation(t *testing.T) {
	fake := newFakeRegistry()
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"id": "u-kg"}), "nothing to update")
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"id": "u-kg", "token": "kg", "aliases": []any{}}), "either 'id' or 'token'")
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"aliases": []any{}}), "'id' or 'token' is required")
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"token": "nope", "aliases": []any{}}), "not found")
}

func TestDeactivateUnitById(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "deactivate_unit", map[string]any{"id": "u-kg"})
	var out map[string]any
	decode(t, res, &out)
	if out["id"] != "u-kg" || out["status"] != "DISABLED" {
		t.Fatalf("unexpected output: %v", out)
	}
	if fake.lastDelete.GetId() != "u-kg" || fake.lastDelete.GetDeletedBy() != "mcp:test" || fake.auth["DeleteUnit"] == "" {
		t.Fatalf("unexpected delete: %+v auth=%q", fake.lastDelete, fake.auth["DeleteUnit"])
	}
}

func TestGetUnitByTokenIsAnOpenRead(t *testing.T) {
	fake := newFakeRegistry()
	var out unitView
	decode(t, callRegistry(t, fake, "get_unit", map[string]any{"token": "kg"}), &out)
	if out.ID != "u-kg" || out.Types[0] != "CAPACITY" || fake.auth["GetUnit"] != "" {
		t.Fatalf("unexpected: %+v auth=%q", out, fake.auth["GetUnit"])
	}
	wantError(t, callRegistry(t, fake, "get_unit", map[string]any{"token": "nope"}), "not found")
}
