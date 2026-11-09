package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"account-service/internal/auth"
	"account-service/internal/db"
)

type fakeGroupStore struct {
	groups  map[string]*db.Group
	members map[string][]string
	users   map[string]bool
	seq     int
}

func newFakeGroupStore() *fakeGroupStore {
	return &fakeGroupStore{
		groups:  map[string]*db.Group{},
		members: map[string][]string{},
		users:   map[string]bool{"alice@example.com": true},
	}
}

func (f *fakeGroupStore) List() ([]db.GroupSummary, error) {
	out := []db.GroupSummary{}
	for id, g := range f.groups {
		out = append(out, db.GroupSummary{Group: *g, MemberCount: int64(len(f.members[id]))})
	}
	return out, nil
}
func (f *fakeGroupStore) Get(id string) (*db.Group, []db.GroupMemberView, error) {
	g, ok := f.groups[id]
	if !ok {
		return nil, nil, db.ErrGroupNotFound
	}
	ms := []db.GroupMemberView{}
	for _, e := range f.members[id] {
		ms = append(ms, db.GroupMemberView{Email: e, IsAllowed: true})
	}
	return g, ms, nil
}
func (f *fakeGroupStore) Create(name, description, by string) (*db.Group, error) {
	for _, g := range f.groups {
		if g.Name == name {
			return nil, db.ErrGroupNameTaken
		}
	}
	f.seq++
	id := strings.Repeat("0", 35) + string(rune('0'+f.seq))
	g := &db.Group{ID: id, Name: name, Description: description, CreatedBy: by}
	f.groups[id] = g
	return g, nil
}
func (f *fakeGroupStore) Update(id, name, description string) (*db.Group, error) {
	g, ok := f.groups[id]
	if !ok {
		return nil, db.ErrGroupNotFound
	}
	g.Name, g.Description = name, description
	return g, nil
}
func (f *fakeGroupStore) Delete(id string) error {
	if _, ok := f.groups[id]; !ok {
		return db.ErrGroupNotFound
	}
	delete(f.groups, id)
	delete(f.members, id)
	return nil
}
func (f *fakeGroupStore) AddMember(id, email, by string) error {
	if _, ok := f.groups[id]; !ok {
		return db.ErrGroupNotFound
	}
	if !f.users[email] {
		return db.ErrUnknownUser
	}
	f.members[id] = append(f.members[id], email)
	return nil
}
func (f *fakeGroupStore) RemoveMember(id, email string) error {
	if _, ok := f.groups[id]; !ok {
		return db.ErrGroupNotFound
	}
	return nil
}

func groupMux(store GroupStore, audit GroupAuditFn) *http.ServeMux {
	h := NewAdminGroupHandlers(AdminGroupDeps{Repo: store, Audit: audit})
	mux := http.NewServeMux()
	mux.HandleFunc("GET /g", h.List)
	mux.HandleFunc("POST /g", h.Create)
	mux.HandleFunc("GET /g/{id}", h.Get)
	mux.HandleFunc("PUT /g/{id}", h.Update)
	mux.HandleFunc("DELETE /g/{id}", h.Delete)
	mux.HandleFunc("POST /g/{id}/members", h.AddMember)
	mux.HandleFunc("DELETE /g/{id}/members/{email}", h.RemoveMember)
	return mux
}

func call(t *testing.T, mux http.Handler, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r = r.WithContext(context.WithValue(r.Context(), authSessionKey, &auth.SessionData{Email: "admin@example.com"}))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)
	return w
}

func TestAdminGroups_CreateValidatesAndAudits(t *testing.T) {
	store := newFakeGroupStore()
	var events []string
	mux := groupMux(store, func(actor, action, target string) { events = append(events, actor+" "+action) })

	if w := call(t, mux, "POST", "/g", `{"name":"  "}`); w.Code != http.StatusBadRequest {
		t.Fatalf("blank name: %d", w.Code)
	}
	if w := call(t, mux, "POST", "/g", `{"name":"`+strings.Repeat("x", 121)+`"}`); w.Code != http.StatusBadRequest {
		t.Fatalf("long name: %d", w.Code)
	}
	w := call(t, mux, "POST", "/g", `{"name":" Équipe prix ","description":"Relevés"}`)
	if w.Code != http.StatusCreated {
		t.Fatalf("create: %d %s", w.Code, w.Body)
	}
	var got map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["name"] != "Équipe prix" || got["created_by"] != "admin@example.com" {
		t.Fatalf("body: %v", got)
	}
	if w := call(t, mux, "POST", "/g", `{"name":"Équipe prix"}`); w.Code != http.StatusConflict {
		t.Fatalf("duplicate: %d", w.Code)
	}
	if len(events) != 1 || events[0] != "admin@example.com group.create" {
		t.Fatalf("audit: %v", events)
	}
}

func TestAdminGroups_MembersAndErrors(t *testing.T) {
	store := newFakeGroupStore()
	mux := groupMux(store, nil)
	w := call(t, mux, "POST", "/g", `{"name":"Data"}`)
	var g map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &g)
	id := g["id"].(string)

	if w := call(t, mux, "POST", "/g/"+id+"/members", `{"email":"nobody@example.com"}`); w.Code != http.StatusNotFound ||
		!strings.Contains(w.Body.String(), "unknown_user") {
		t.Fatalf("unknown user: %d %s", w.Code, w.Body)
	}
	if w := call(t, mux, "POST", "/g/"+id+"/members", `{"email":"not-an-email"}`); w.Code != http.StatusBadRequest {
		t.Fatalf("bad email: %d", w.Code)
	}
	if w := call(t, mux, "POST", "/g/"+id+"/members", `{"email":"alice@example.com"}`); w.Code != http.StatusOK {
		t.Fatalf("add: %d %s", w.Code, w.Body)
	}
	w = call(t, mux, "GET", "/g/"+id, "")
	if w.Code != http.StatusOK || !strings.Contains(w.Body.String(), `"member_count":1`) {
		t.Fatalf("get: %d %s", w.Code, w.Body)
	}
	if w := call(t, mux, "DELETE", "/g/"+id+"/members/alice@example.com", ""); w.Code != http.StatusNoContent {
		t.Fatalf("remove: %d", w.Code)
	}
	if w := call(t, mux, "GET", "/g/missing", ""); w.Code != http.StatusNotFound {
		t.Fatalf("missing: %d", w.Code)
	}
	if w := call(t, mux, "DELETE", "/g/"+id, ""); w.Code != http.StatusNoContent {
		t.Fatalf("delete: %d", w.Code)
	}
	if w := call(t, mux, "PUT", "/g/"+id, `{"name":"x"}`); w.Code != http.StatusNotFound {
		t.Fatalf("update deleted: %d", w.Code)
	}
}

type fakeDirectory struct{}

func (fakeDirectory) Directory() ([]db.User, []db.Group, []db.GroupMember, error) {
	return []db.User{{Email: "alice@example.com", DisplayName: "Alice", IsAllowed: true},
			{Email: "bob@example.com", IsAllowed: false}},
		[]db.Group{{ID: "g1", Name: "Data"}, {ID: "g2", Name: "Vide"}},
		[]db.GroupMember{{GroupID: "g1", UserEmail: "alice@example.com"}},
		nil
}

func TestInternalDirectory_TokenAndShape(t *testing.T) {
	h := NewInternalDirectoryHandler(InternalDirectoryDeps{Repo: fakeDirectory{}, AdminToken: "secret"})

	r := httptest.NewRequest("GET", "/internal/directory", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("no token: %d", w.Code)
	}

	r = httptest.NewRequest("GET", "/internal/directory", nil)
	r.Header.Set("X-Admin-Token", "secret")
	w = httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK || w.Header().Get("Content-Type") != "application/json" {
		t.Fatalf("ok: %d %q", w.Code, w.Header().Get("Content-Type"))
	}
	var got struct {
		Users []struct {
			Email     string `json:"email"`
			IsAllowed bool   `json:"is_allowed"`
		} `json:"users"`
		Groups []struct {
			ID      string   `json:"id"`
			Members []string `json:"members"`
		} `json:"groups"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if len(got.Users) != 2 || got.Users[1].IsAllowed {
		t.Fatalf("users: %+v", got.Users)
	}
	if len(got.Groups) != 2 || len(got.Groups[0].Members) != 1 || got.Groups[1].Members == nil {
		t.Fatalf("groups (empty group must have [] members): %+v", got.Groups)
	}

	empty := NewInternalDirectoryHandler(InternalDirectoryDeps{Repo: fakeDirectory{}, AdminToken: ""})
	r = httptest.NewRequest("GET", "/internal/directory", nil)
	r.Header.Set("X-Admin-Token", "")
	w = httptest.NewRecorder()
	empty.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("unset server token must refuse: %d", w.Code)
	}
}
