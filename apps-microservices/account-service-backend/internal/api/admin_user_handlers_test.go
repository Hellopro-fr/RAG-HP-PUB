package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"account-service/internal/db"
	"account-service/internal/gatewaysync"
)

type fakeUserAdminRepo struct {
	users []db.User
	last  string
}

func (f *fakeUserAdminRepo) List(limit, offset int) ([]db.User, int64, error) {
	return f.users, int64(len(f.users)), nil
}
func (f *fakeUserAdminRepo) FindByEmail(email string) (*db.User, error) {
	for i := range f.users {
		if f.users[i].Email == email {
			return &f.users[i], nil
		}
	}
	return nil, errors.New("not found")
}
func (f *fakeUserAdminRepo) SetAdmin(email string, admin bool) error {
	for i := range f.users {
		if f.users[i].Email == email {
			f.users[i].IsAdmin = admin
			f.last = "admin"
			return nil
		}
	}
	return errors.New("not found")
}
func (f *fakeUserAdminRepo) SetAllowed(email string, ok bool) error {
	for i := range f.users {
		if f.users[i].Email == email {
			f.users[i].IsAllowed = ok
			f.last = "allowed"
			return nil
		}
	}
	return errors.New("not found")
}
func (f *fakeUserAdminRepo) ListAllowed() ([]db.User, error) {
	out := []db.User{}
	for _, u := range f.users {
		if u.IsAllowed {
			out = append(out, u)
		}
	}
	return out, nil
}

type fakeRevokeAll struct {
	called string
}

func (f *fakeRevokeAll) RevokeAllForUser(email, reason string) error {
	f.called = email
	return nil
}

type fakeBroadcast struct {
	users []string
}

func (f *fakeBroadcast) BroadcastForUser(email string) {
	f.users = append(f.users, email)
}

func TestAdminUsers_PromoteDemoteBlockUnblock(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	h := NewAdminUserHandler(AdminUserDeps{
		Repo:        repo,
		RevokeAll:   &fakeRevokeAll{},
		Broadcaster: &fakeBroadcast{},
	})

	cases := []struct {
		op      string
		check   func() bool
		message string
	}{
		{"promote", func() bool { return repo.users[0].IsAdmin }, "promote did not set IsAdmin=true"},
		{"demote", func() bool { return !repo.users[0].IsAdmin }, "demote did not set IsAdmin=false"},
		{"block", func() bool { return !repo.users[0].IsAllowed }, "block did not set IsAllowed=false"},
		{"unblock", func() bool { return repo.users[0].IsAllowed }, "unblock did not set IsAllowed=true"},
	}
	for _, c := range cases {
		r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/"+c.op, nil)
		r.SetPathValue("email", "alice@x")
		r.SetPathValue("op", c.op)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != http.StatusOK {
			t.Fatalf("op=%s Code=%d body=%s", c.op, w.Code, w.Body.String())
		}
		if !c.check() {
			t.Fatalf("op=%s: %s", c.op, c.message)
		}
	}
}

func TestAdminUsers_RevokeAllSessions(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	rev := &fakeRevokeAll{}
	bc := &fakeBroadcast{}
	h := NewAdminUserHandler(AdminUserDeps{
		Repo:        repo,
		RevokeAll:   rev,
		Broadcaster: bc,
	})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/revoke", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "revoke")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	if rev.called != "alice@x" {
		t.Fatal("RevokeAll not called")
	}
	if len(bc.users) != 1 || bc.users[0] != "alice@x" {
		t.Fatalf("broadcast users=%v", bc.users)
	}

	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "revoked" {
		t.Errorf("status=%v", body["status"])
	}
}

type fakeMcpSync struct {
	got []gatewaysync.SyncUser
	res *gatewaysync.Result
	err error
}

func (f *fakeMcpSync) SyncUsers(users []gatewaysync.SyncUser) (*gatewaysync.Result, error) {
	f.got = users
	if f.err != nil {
		return nil, f.err
	}
	return f.res, nil
}

func TestAdminUsers_SyncMcp_SingleUser(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x", DisplayName: "Alice", IsAllowed: false}}}
	sync := &fakeMcpSync{res: &gatewaysync.Result{Created: []string{"alice@x"}, Skipped: []string{}}}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/sync-mcp", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	// Per-row sync works even for a blocked user (explicit admin intent).
	if len(sync.got) != 1 || sync.got[0].Email != "alice@x" || sync.got[0].DisplayName != "Alice" {
		t.Fatalf("synced = %+v", sync.got)
	}
	var res gatewaysync.Result
	_ = json.Unmarshal(w.Body.Bytes(), &res)
	if len(res.Created) != 1 || res.Created[0] != "alice@x" {
		t.Errorf("created = %v", res.Created)
	}
}

func TestAdminUsers_SyncMcp_UnknownUser404(t *testing.T) {
	repo := &fakeUserAdminRepo{}
	sync := &fakeMcpSync{res: &gatewaysync.Result{}}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/ghost@x/sync-mcp", nil)
	r.SetPathValue("email", "ghost@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusNotFound {
		t.Fatalf("Code=%d, want 404", w.Code)
	}
	if sync.got != nil {
		t.Error("gateway must not be called for unknown user")
	}
}

func TestAdminUsers_SyncMcp_Unconfigured503(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: nil})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/sync-mcp", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("Code=%d, want 503", w.Code)
	}
}

func TestAdminUsers_SyncMcp_GatewayError502(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "alice@x"}}}
	sync := &fakeMcpSync{err: errors.New("connection refused")}
	h := NewAdminUserHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/alice@x/sync-mcp", nil)
	r.SetPathValue("email", "alice@x")
	r.SetPathValue("op", "sync-mcp")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusBadGateway {
		t.Fatalf("Code=%d, want 502", w.Code)
	}
}

func TestAdminUsersSyncAll_FiltersAllowedOnly(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{
		{Email: "ok@x", DisplayName: "OK", IsAllowed: true},
		{Email: "blocked@x", DisplayName: "Blocked", IsAllowed: false},
	}}
	sync := &fakeMcpSync{res: &gatewaysync.Result{Created: []string{"ok@x"}, Skipped: []string{}}}
	h := NewAdminUserMcpSyncAllHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/sync-mcp", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	if len(sync.got) != 1 || sync.got[0].Email != "ok@x" {
		t.Fatalf("synced = %+v, want only ok@x", sync.got)
	}
}

func TestAdminUsersSyncAll_NoAllowedUsers_SkipsGatewayCall(t *testing.T) {
	repo := &fakeUserAdminRepo{users: []db.User{{Email: "blocked@x", IsAllowed: false}}}
	sync := &fakeMcpSync{res: &gatewaysync.Result{}}
	h := NewAdminUserMcpSyncAllHandler(AdminUserDeps{Repo: repo, RevokeAll: &fakeRevokeAll{}, Broadcaster: &fakeBroadcast{}, McpSync: sync})

	r := httptest.NewRequest(http.MethodPost, "/api/v1/admin/users/sync-mcp", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	if sync.got != nil {
		t.Error("gateway must not be called with an empty batch")
	}
	if !strings.Contains(w.Body.String(), `"created":[]`) {
		t.Errorf("body = %s, want empty created/skipped", w.Body.String())
	}
}
