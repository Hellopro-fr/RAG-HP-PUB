package transport

import (
	"net/http/httptest"
	"reflect"
	"testing"
)

func TestEnrichRequestContext_HeaderAbsent(t *testing.T) {
	r := httptest.NewRequest("GET", "/sse", nil)
	ctx := enrichRequestContext(r)
	if _, restricted := AllowedParticipantsFromContext(ctx); restricted {
		t.Error("absent header should yield unrestricted ctx")
	}
}

func TestEnrichRequestContext_HeaderPresent(t *testing.T) {
	r := httptest.NewRequest("GET", "/sse", nil)
	r.Header.Set(AllowedParticipantsHeader, "uuid-a, uuid-b")
	ctx := enrichRequestContext(r)
	got, restricted := AllowedParticipantsFromContext(ctx)
	if !restricted {
		t.Fatal("expected restricted=true")
	}
	if !reflect.DeepEqual(got, []string{"uuid-a", "uuid-b"}) {
		t.Errorf("got %v", got)
	}
}

func TestEnrichRequestContext_HeaderPresentButEmpty(t *testing.T) {
	// Non-empty header that parses to zero valid UUIDs → deny-all.
	r := httptest.NewRequest("GET", "/sse", nil)
	r.Header.Set(AllowedParticipantsHeader, " , , ")
	ctx := enrichRequestContext(r)
	got, restricted := AllowedParticipantsFromContext(ctx)
	if !restricted {
		t.Fatal("expected restricted=true (deny-all), got unrestricted")
	}
	if len(got) != 0 {
		t.Errorf("expected empty allow-list, got %v", got)
	}
}

func TestWithAllowedParticipantsForTest_Unrestricted(t *testing.T) {
	ctx := WithAllowedParticipantsForTest(nil, nil, false)
	_ = ctx // ensure signature compiles; absent header = no-op
}

func TestParseAllowedParticipantsHeader(t *testing.T) {
	cases := map[string][]string{
		"":                    nil,
		"uuid-a":              {"uuid-a"},
		"uuid-a,uuid-b":       {"uuid-a", "uuid-b"},
		" uuid-a , uuid-b  ":  {"uuid-a", "uuid-b"},
		",,":                  {},
		"  ,uuid-a,,uuid-b,,": {"uuid-a", "uuid-b"},
	}
	for in, want := range cases {
		got := parseAllowedParticipantsHeader(in)
		if len(got) == 0 && len(want) == 0 {
			continue
		}
		if !reflect.DeepEqual(got, want) {
			t.Errorf("parse(%q) = %v, want %v", in, got, want)
		}
	}
}
