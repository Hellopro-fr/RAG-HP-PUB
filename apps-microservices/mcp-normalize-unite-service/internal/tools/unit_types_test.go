package tools

import (
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestCreateUnitTypeForwardsWithTheBearer(t *testing.T) {
	fake := newFakeRegistry()
	var out unitTypeView
	decode(t, callRegistry(t, fake, "create_unit_type", map[string]any{"code": "POIDS", "label": "Poids", "description": "Masse"}), &out)
	if out.Code != "POIDS" || !out.IsActive || len(out.Dimensions) != 0 {
		t.Fatalf("unexpected view: %+v", out)
	}
	spec := fake.lastCreateT.GetSpec()
	if spec.GetLabel() != "Poids" || spec.GetDescription() != "Masse" || fake.lastCreateT.GetCreatedBy() != "mcp:test" {
		t.Fatalf("unexpected request: %+v", fake.lastCreateT)
	}
	if fake.auth["CreateUnitType"] != "Bearer "+testAdminKey {
		t.Fatalf("missing bearer")
	}
}

func TestCreateUnitTypeValidation(t *testing.T) {
	fake := newFakeRegistry()
	wantError(t, callRegistry(t, fake, "create_unit_type", map[string]any{"label": "Poids"}), "'code'")
	wantError(t, callRegistry(t, fake, "create_unit_type", map[string]any{"code": "POIDS"}), "'label'")
	if len(fake.calls) != 0 {
		t.Fatalf("backend called: %v", fake.calls)
	}
}

func TestGetUnitTypeListsWhenNoReferenceIsGiven(t *testing.T) {
	fake := newFakeRegistry()
	var out []unitTypeView
	decode(t, callRegistry(t, fake, "get_unit_type", map[string]any{}), &out)
	if len(out) != 1 || out[0].Code != "CAPACITY" || fake.calls[0] != "ListUnitTypes" {
		t.Fatalf("unexpected: %+v calls=%v", out, fake.calls)
	}
	var one unitTypeView
	decode(t, callRegistry(t, fake, "get_unit_type", map[string]any{"code": "CAPACITY"}), &one)
	if one.ID != "t-cap" || fake.lastGetT.GetCode() != "CAPACITY" || fake.auth["GetUnitType"] != "" {
		t.Fatalf("unexpected: %+v", one)
	}
}

func TestUpdateUnitTypeByCodeSendsALabelMask(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "update_unit_type", map[string]any{"code": "CAPACITY", "label": "Contenance"})
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content[0].Text)
	}
	if fake.lastUpdateT.GetId() != "t-cap" || fake.lastUpdateT.GetSpec().GetLabel() != "Contenance" {
		t.Fatalf("unexpected update: %+v", fake.lastUpdateT)
	}
	if paths := fake.lastUpdateT.GetUpdateMask().GetPaths(); len(paths) != 1 || paths[0] != "label" {
		t.Fatalf("mask = %v", paths)
	}
	wantError(t, callRegistry(t, fake, "update_unit_type", map[string]any{"code": "CAPACITY"}), "nothing to update")
}

func TestDeactivateUnitTypeById(t *testing.T) {
	fake := newFakeRegistry()
	var out unitTypeView
	decode(t, callRegistry(t, fake, "deactivate_unit_type", map[string]any{"id": "t-cap"}), &out)
	if out.IsActive || fake.lastDeactT.GetId() != "t-cap" || fake.auth["DeactivateUnitType"] == "" {
		t.Fatalf("unexpected: %+v", out)
	}
}

func TestSetDimensionTypesAllowsAnEmptyListToClear(t *testing.T) {
	fake := newFakeRegistry()
	var out map[string]any
	decode(t, callRegistry(t, fake, "set_dimension_types", map[string]any{"dimension": "volume", "type_codes": []any{}}), &out)
	if fake.lastSetDims.GetDimension() != "volume" || len(fake.lastSetDims.GetTypeCodes()) != 0 {
		t.Fatalf("unexpected request: %+v", fake.lastSetDims)
	}
	if codes, ok := out["type_codes"].([]any); !ok || len(codes) != 0 {
		t.Fatalf("type_codes must be an empty array, got %v", out["type_codes"])
	}
	wantError(t, callRegistry(t, fake, "set_dimension_types", map[string]any{"dimension": "volume"}), "'type_codes' parameter is required")
}

func TestUnitTypeServerErrorsPassThrough(t *testing.T) {
	fake := newFakeRegistry()
	fake.err = status.Error(codes.FailedPrecondition, "type CAPACITY is inactive")
	wantError(t, callRegistry(t, fake, "set_dimension_types", map[string]any{"dimension": "volume", "type_codes": []any{"CAPACITY"}}), "is inactive")
}
