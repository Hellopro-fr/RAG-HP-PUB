package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
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
