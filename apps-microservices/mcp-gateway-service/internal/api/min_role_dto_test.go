package api

import "testing"

func TestValidMinRole(t *testing.T) {
	valid := []string{"", "config-only", "read-only", "admin"}
	for _, v := range valid {
		if !ValidMinRole(v) {
			t.Fatalf("ValidMinRole(%q) = false, want true", v)
		}
	}
	invalid := []string{"wizard", "Admin", "ADMIN", "readonly", "read_only", " admin", "admin "}
	for _, v := range invalid {
		if ValidMinRole(v) {
			t.Fatalf("ValidMinRole(%q) = true, want false", v)
		}
	}
}
