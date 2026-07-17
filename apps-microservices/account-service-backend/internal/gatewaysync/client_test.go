package gatewaysync

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSyncUsers_SendsTokenAndBody_ParsesResult(t *testing.T) {
	var gotToken string
	var gotBody struct {
		Users []SyncUser `json:"users"`
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/api/v1/internal/users/sync" {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		gotToken = r.Header.Get("X-Admin-Token")
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"created":["a@x"],"skipped":["b@x"]}`))
	}))
	defer srv.Close()

	c := New(srv.URL+"/", "secret") // trailing slash must be tolerated
	res, err := c.SyncUsers([]SyncUser{{Email: "a@x", DisplayName: "A"}, {Email: "b@x", DisplayName: "B"}})
	if err != nil {
		t.Fatalf("SyncUsers: %v", err)
	}
	if gotToken != "secret" {
		t.Errorf("X-Admin-Token = %q", gotToken)
	}
	if len(gotBody.Users) != 2 || gotBody.Users[0].Email != "a@x" {
		t.Errorf("body users = %+v", gotBody.Users)
	}
	if len(res.Created) != 1 || res.Created[0] != "a@x" || len(res.Skipped) != 1 || res.Skipped[0] != "b@x" {
		t.Errorf("result = %+v", res)
	}
}

func TestSyncUsers_Non200_ReturnsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
	}))
	defer srv.Close()

	c := New(srv.URL, "bad")
	if _, err := c.SyncUsers([]SyncUser{{Email: "a@x"}}); err == nil {
		t.Fatal("want error on HTTP 401, got nil")
	}
}

func TestSyncUsers_ConnectionRefused_ReturnsError(t *testing.T) {
	c := New("http://127.0.0.1:1", "tok")
	if _, err := c.SyncUsers([]SyncUser{{Email: "a@x"}}); err == nil {
		t.Fatal("want connection error, got nil")
	}
}
