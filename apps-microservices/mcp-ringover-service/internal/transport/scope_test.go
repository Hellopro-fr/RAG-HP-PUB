package transport

import (
	"context"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
)

func TestParseAllowedUserIDsHeader(t *testing.T) {
	cases := []struct {
		in   string
		want []int
	}{
		{"", nil},
		{"  ", nil},
		{"123", []int{123}},
		{"123,456,789", []int{123, 456, 789}},
		{" 123 , 456 ", []int{123, 456}},
		{"123,,456", []int{123, 456}},
		{"0,123", []int{123}},          // 0 is invalid (sentinel "deny-all")
		{"-1,42", []int{42}},           // negative IDs rejected
		{"abc,42", []int{42}},          // non-numeric rejected
		{"42,abc,100", []int{42, 100}}, // mixed valid/invalid
	}
	for _, c := range cases {
		got := parseAllowedUserIDsHeader(c.in)
		if !reflect.DeepEqual(got, c.want) {
			t.Errorf("parseAllowedUserIDsHeader(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestAllowedUserIDsFromContext_NoHeader(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	ctx := enrichRequestContext(req)

	ids, restricted := AllowedUserIDsFromContext(ctx)
	if restricted {
		t.Errorf("expected unrestricted when header absent, got restricted=true")
	}
	if ids != nil {
		t.Errorf("expected nil ids when unrestricted, got %v", ids)
	}
}

func TestAllowedUserIDsFromContext_ValidHeader(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set(AllowedUserIDsHeader, "123,456")
	ctx := enrichRequestContext(req)

	ids, restricted := AllowedUserIDsFromContext(ctx)
	if !restricted {
		t.Fatalf("expected restricted=true when header is set")
	}
	want := []int{123, 456}
	if !reflect.DeepEqual(ids, want) {
		t.Errorf("ids = %v, want %v", ids, want)
	}
}

func TestAllowedUserIDsFromContext_DenyAll(t *testing.T) {
	// A header set to a sentinel/invalid value declares scope but resolves to
	// no valid IDs — this must be treated as "deny all", not "unrestricted".
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set(AllowedUserIDsHeader, "0")
	ctx := enrichRequestContext(req)

	ids, restricted := AllowedUserIDsFromContext(ctx)
	if !restricted {
		t.Fatalf("expected restricted=true even for deny-all sentinel")
	}
	if len(ids) != 0 {
		t.Errorf("expected empty ids for deny-all, got %v", ids)
	}
}

func TestWithAllowedUserIDs_NotRestricted(t *testing.T) {
	// withAllowedUserIDs with restricted=false is a no-op.
	ctx := withAllowedUserIDs(context.Background(), []int{1, 2}, false)
	if _, restricted := AllowedUserIDsFromContext(ctx); restricted {
		t.Error("expected unrestricted context when restricted=false")
	}
}
