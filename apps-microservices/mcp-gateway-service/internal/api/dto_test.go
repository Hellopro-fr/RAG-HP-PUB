package api

import "testing"

func TestToolSummaryStruct(t *testing.T) {
	ts := ToolSummary{Name: "test", IsActive: true}
	if ts.Name != "test" || !ts.IsActive {
		t.Error("unexpected ToolSummary values")
	}
}
