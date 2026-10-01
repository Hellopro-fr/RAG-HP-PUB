package scanner

import "testing"

func TestMergeTargets_EnvOverridesManual(t *testing.T) {
	seeds := map[string]string{"svc-a": "http://a", "svc-b": "http://b"}
	rows := []DBRow{
		{Name: "svc-a", BaseURL: "http://old-a", Source: "manual"},
		{Name: "svc-c", BaseURL: "http://c", Source: "manual"},
	}
	targets := MergeTargets(seeds, rows)
	byName := map[string]Target{}
	for _, t := range targets {
		byName[t.Name] = t
	}
	if byName["svc-a"].BaseURL != "http://a" || byName["svc-a"].Source != "env" {
		t.Fatalf("env should override manual for svc-a, got %+v", byName["svc-a"])
	}
	if byName["svc-c"].BaseURL != "http://c" {
		t.Fatalf("manual-only svc-c should be present, got %+v", byName["svc-c"])
	}
	if len(targets) != 3 {
		t.Fatalf("expected 3 targets, got %d: %+v", len(targets), targets)
	}
}

func TestMergeTargets_SkipsNonManualDB(t *testing.T) {
	seeds := map[string]string{}
	rows := []DBRow{
		{Name: "auto-svc", BaseURL: "http://auto", Source: "env"},
	}
	targets := MergeTargets(seeds, rows)
	if len(targets) != 0 {
		t.Fatalf("non-manual DB row should be skipped, got %+v", targets)
	}
}
