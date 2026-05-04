package authserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestMetadataEndpoint(t *testing.T) {
	h := NewMetadataHandler("https://account.test")
	r := httptest.NewRequest(http.MethodGet, "/.well-known/oauth-authorization-server", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["issuer"] != "https://account.test" {
		t.Errorf("issuer=%v", got["issuer"])
	}
	if got["authorization_endpoint"] != "https://account.test/authorize" {
		t.Errorf("authorization_endpoint=%v", got["authorization_endpoint"])
	}
	methods, _ := got["code_challenge_methods_supported"].([]interface{})
	if len(methods) == 0 || methods[0] != "S256" {
		t.Errorf("code_challenge_methods_supported=%v", methods)
	}
}
