package api

import "testing"

func TestStripToolPrefix(t *testing.T) {
	tests := []struct {
		prefix, toolName, expected string
	}{
		{"zoho", "zoho_search", "search"},
		{"zoho", "other_search", "other_search"},
		{"", "search", "search"},
	}
	for _, tt := range tests {
		got := stripToolPrefix(tt.prefix, tt.toolName)
		if got != tt.expected {
			t.Errorf("stripToolPrefix(%q, %q) = %q, want %q", tt.prefix, tt.toolName, got, tt.expected)
		}
	}
}
