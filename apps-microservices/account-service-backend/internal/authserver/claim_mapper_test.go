package authserver

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestApplyClaimMappings_DefaultsWhenEmpty(t *testing.T) {
	user := UserClaimSource{Email: "a@x", DisplayName: "Alice", IsAdmin: true}
	got := ApplyClaimMappings("", user)
	want := map[string]interface{}{
		"sub":   "a@x",
		"email": "a@x",
		"name":  "Alice",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got=%v want=%v", got, want)
	}
}

func TestApplyClaimMappings_CustomMapping(t *testing.T) {
	mapping, _ := json.Marshal(map[string]string{"email": "user_email", "is_admin": "role_admin"})
	got := ApplyClaimMappings(string(mapping), UserClaimSource{Email: "a@x", IsAdmin: true})
	if got["user_email"] != "a@x" {
		t.Errorf("user_email=%v", got["user_email"])
	}
	if got["role_admin"] != true {
		t.Errorf("role_admin=%v", got["role_admin"])
	}
	if _, found := got["sub"]; !found {
		t.Error("sub default missing")
	}
}
