package tools

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"

	"google.golang.org/grpc"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	normalizationpb "github.com/hellopro/mcp-normalize-unite/proto/gen/graph_normalization"
)

// fakeNormalization records requests and answers NormalizeQuantity from a table
// keyed by value; NormalizeRange must never be called by the tools.
type fakeNormalization struct {
	mu        sync.Mutex
	requests  []*normalizationpb.NormalizeQuantityRequest
	responses map[string]*normalizationpb.NormalizeQuantityResponse
	err       error
	rangeHits int
}

func (f *fakeNormalization) NormalizeQuantity(ctx context.Context, in *normalizationpb.NormalizeQuantityRequest, _ ...grpc.CallOption) (*normalizationpb.NormalizeQuantityResponse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.requests = append(f.requests, in)
	if _, ok := ctx.Deadline(); !ok {
		return nil, errors.New("call has no deadline")
	}
	if f.err != nil {
		return nil, f.err
	}
	if resp, ok := f.responses[in.GetValue()]; ok {
		return resp, nil
	}
	return &normalizationpb.NormalizeQuantityResponse{Success: false, ErrorMessage: "Could not normalize value for label '" + in.GetLabel() + "'"}, nil
}

func (f *fakeNormalization) NormalizeRange(context.Context, *normalizationpb.NormalizeRangeRequest, ...grpc.CallOption) (*normalizationpb.NormalizeRangeResponse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.rangeHits++
	return nil, errors.New("NormalizeRange must not be used")
}

func ok(value float64, unit string) *normalizationpb.NormalizeQuantityResponse {
	return &normalizationpb.NormalizeQuantityResponse{Success: true, CanonicalValue: value, CanonicalUnit: unit}
}

// call round-trips args through JSON so handlers see exactly what the MCP
// transport delivers (every number is a float64, never a Go int).
func call(t *testing.T, fake *fakeNormalization, tool string, args map[string]any) *mcp.CallToolResult {
	t.Helper()
	raw, err := json.Marshal(args)
	if err != nil {
		t.Fatalf("marshal args: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal args: %v", err)
	}
	r := NewRegistry(&Clients{Normalization: fake})
	return r.CallTool(context.Background(), &mcp.CallToolParams{Name: tool, Arguments: decoded})
}

func decode(t *testing.T, res *mcp.CallToolResult, v any) {
	t.Helper()
	if res.IsError {
		t.Fatalf("unexpected error result: %s", res.Content[0].Text)
	}
	if err := json.Unmarshal([]byte(res.Content[0].Text), v); err != nil {
		t.Fatalf("result is not JSON: %v\n%s", err, res.Content[0].Text)
	}
}

func wantError(t *testing.T, res *mcp.CallToolResult, substr string) {
	t.Helper()
	if !res.IsError {
		t.Fatalf("expected error containing %q, got success: %s", substr, res.Content[0].Text)
	}
	if !strings.Contains(res.Content[0].Text, substr) {
		t.Fatalf("expected error containing %q, got %q", substr, res.Content[0].Text)
	}
}

func TestToolsList(t *testing.T) {
	r := NewRegistry(&Clients{Normalization: &fakeNormalization{}})
	tools := r.ListTools()
	names := []string{}
	for _, tl := range tools {
		names = append(names, tl.Name)
		var schema map[string]any
		if err := json.Unmarshal(tl.InputSchema, &schema); err != nil {
			t.Fatalf("tool %s has invalid JSON schema: %v", tl.Name, err)
		}
		if schema["type"] != "object" {
			t.Fatalf("tool %s schema type = %v", tl.Name, schema["type"])
		}
	}
	if strings.Join(names, ",") != "normalize_quantity,normalize_range,create_unit,update_unit,deactivate_unit,get_unit,create_unit_type,update_unit_type,deactivate_unit_type,get_unit_type,set_dimension_types" {
		t.Fatalf("tools = %v", names)
	}
}

func TestNormalizeQuantitySuccessForwardsFieldsAndDefaultsDataType(t *testing.T) {
	fake := &fakeNormalization{responses: map[string]*normalizationpb.NormalizeQuantityResponse{"2.5": ok(2500, "kg")}}
	res := call(t, fake, "normalize_quantity", map[string]any{"label": " Poids ", "value": 2.5, "unit": "t"})

	var got quantityResult
	decode(t, res, &got)
	if got.CanonicalValue != 2500 || got.CanonicalUnit != "kg" || got.Label != "Poids" || got.Value != "2.5" || got.Unit != "t" {
		t.Fatalf("unexpected result: %+v", got)
	}
	req := fake.requests[0]
	if req.GetLabel() != "Poids" || req.GetUnit() != "t" || req.GetValue() != "2.5" || req.GetDataType() != "numeric" {
		t.Fatalf("unexpected request: %+v", req)
	}
}

func TestNormalizeQuantityStringValuePassesThroughVerbatim(t *testing.T) {
	fake := &fakeNormalization{responses: map[string]*normalizationpb.NormalizeQuantityResponse{"+/- 2": ok(0.002, "m")}}
	res := call(t, fake, "normalize_quantity", map[string]any{"label": "Tolérance", "value": "+/- 2", "unit": "mm", "data_type": "numeric_range"})

	var got quantityResult
	decode(t, res, &got)
	if fake.requests[0].GetValue() != "+/- 2" || fake.requests[0].GetDataType() != "numeric_range" {
		t.Fatalf("unexpected request: %+v", fake.requests[0])
	}
}

func TestNormalizeQuantityLargeNumberIsNotScientific(t *testing.T) {
	fake := &fakeNormalization{responses: map[string]*normalizationpb.NormalizeQuantityResponse{"25000000": ok(25000, "kg")}}
	res := call(t, fake, "normalize_quantity", map[string]any{"label": "Poids", "value": 2.5e7, "unit": "g"})
	var got quantityResult
	decode(t, res, &got)
}

func TestNormalizeQuantityBackendFailureIsToolError(t *testing.T) {
	fake := &fakeNormalization{}
	res := call(t, fake, "normalize_quantity", map[string]any{"label": "Poids", "value": "12", "unit": "furlong"})
	wantError(t, res, "Could not normalize value for label 'Poids'")
	wantError(t, res, `unit="furlong"`)
}

func TestNormalizeQuantityGRPCErrorIsToolError(t *testing.T) {
	fake := &fakeNormalization{err: errors.New("connection refused")}
	res := call(t, fake, "normalize_quantity", map[string]any{"label": "Poids", "value": "12", "unit": "kg"})
	wantError(t, res, "connection refused")
}

func TestNormalizeQuantityValidation(t *testing.T) {
	cases := []struct {
		name string
		args map[string]any
		want string
	}{
		{"missing label", map[string]any{"value": 1}, "'label' parameter is required"},
		{"blank label", map[string]any{"label": "  ", "value": 1}, "'label' must not be empty"},
		{"label not string", map[string]any{"label": 3, "value": 1}, "'label' must be a string"},
		{"missing value", map[string]any{"label": "Poids"}, "'value' parameter is required"},
		{"blank value", map[string]any{"label": "Poids", "value": " "}, "'value' must not be empty"},
		{"bool value", map[string]any{"label": "Poids", "value": true}, "'value' must be a number or a string"},
		{"unit not string", map[string]any{"label": "Poids", "value": 1, "unit": 5}, "'unit' must be a string"},
		{"bad data_type", map[string]any{"label": "Poids", "value": 1, "data_type": "text"}, "'data_type' must be one of numeric, numeric_range"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			fake := &fakeNormalization{}
			wantError(t, call(t, fake, "normalize_quantity", tc.args), tc.want)
			if len(fake.requests) != 0 {
				t.Fatalf("invalid input reached the backend: %+v", fake.requests)
			}
		})
	}
}

func TestNormalizeRangeBothBounds(t *testing.T) {
	fake := &fakeNormalization{responses: map[string]*normalizationpb.NormalizeQuantityResponse{
		"10": ok(0.1, "m"),
		"50": ok(0.5, "m"),
	}}
	res := call(t, fake, "normalize_range", map[string]any{"label": "Longueur", "min_value": 10.0, "max_value": "50", "unit": "cm"})

	var got rangeResult
	decode(t, res, &got)
	if got.CanonicalMin == nil || *got.CanonicalMin != 0.1 || got.CanonicalMax == nil || *got.CanonicalMax != 0.5 || got.CanonicalUnit != "m" {
		t.Fatalf("unexpected result: %+v", got)
	}
	if len(fake.requests) != 2 || fake.rangeHits != 0 {
		t.Fatalf("expected 2 NormalizeQuantity calls and no NormalizeRange, got %d / %d", len(fake.requests), fake.rangeHits)
	}
	for _, req := range fake.requests {
		if req.GetDataType() != "numeric" || req.GetUnit() != "cm" || req.GetLabel() != "Longueur" {
			t.Fatalf("unexpected request: %+v", req)
		}
	}
}

func TestNormalizeRangeSingleBoundOmitsTheOther(t *testing.T) {
	fake := &fakeNormalization{responses: map[string]*normalizationpb.NormalizeQuantityResponse{"5": ok(5, "bar")}}
	res := call(t, fake, "normalize_range", map[string]any{"label": "Pression", "max_value": 5.0, "unit": "bar"})

	if strings.Contains(res.Content[0].Text, "canonical_min") {
		t.Fatalf("absent bound must be omitted, got %s", res.Content[0].Text)
	}
	var got rangeResult
	decode(t, res, &got)
	if got.CanonicalMax == nil || *got.CanonicalMax != 5 || len(fake.requests) != 1 {
		t.Fatalf("unexpected result: %+v (%d calls)", got, len(fake.requests))
	}
}

// The NormalizeRange RPC would answer success=true with canonical_max=0 here.
func TestNormalizeRangeFailedBoundIsReportedNotZeroed(t *testing.T) {
	fake := &fakeNormalization{responses: map[string]*normalizationpb.NormalizeQuantityResponse{"10": ok(0.1, "m")}}
	res := call(t, fake, "normalize_range", map[string]any{"label": "Longueur", "min_value": 10.0, "max_value": 99.0, "unit": "cm"})
	wantError(t, res, "max_value: Could not normalize")
}

func TestNormalizeRangeValidation(t *testing.T) {
	cases := []struct {
		name string
		args map[string]any
		want string
	}{
		{"no bounds", map[string]any{"label": "Longueur"}, "at least one of 'min_value' or 'max_value' is required"},
		{"blank string bounds", map[string]any{"label": "Longueur", "min_value": "", "max_value": " "}, "at least one of"},
		{"inverted", map[string]any{"label": "Longueur", "min_value": 5.0, "max_value": 1.0}, "must not exceed"},
		{"non numeric", map[string]any{"label": "Longueur", "min_value": "abc"}, "'min_value' must be a number"},
		{"nan string", map[string]any{"label": "Longueur", "max_value": "NaN"}, "'max_value' must be a finite number"},
		{"missing label", map[string]any{"min_value": 1.0}, "'label' parameter is required"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			fake := &fakeNormalization{}
			wantError(t, call(t, fake, "normalize_range", tc.args), tc.want)
			if len(fake.requests) != 0 {
				t.Fatalf("invalid input reached the backend: %+v", fake.requests)
			}
		})
	}
}

func TestUnknownTool(t *testing.T) {
	wantError(t, call(t, &fakeNormalization{}, "normalize_everything", nil), "unknown tool")
}
