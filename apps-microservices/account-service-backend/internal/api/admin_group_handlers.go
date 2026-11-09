package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"unicode/utf8"

	"account-service/internal/db"
)

// GroupStore is the persistence contract of the group (team) admin API.
type GroupStore interface {
	List() ([]db.GroupSummary, error)
	Get(id string) (*db.Group, []db.GroupMemberView, error)
	Create(name, description, createdBy string) (*db.Group, error)
	Update(id, name, description string) (*db.Group, error)
	Delete(id string) error
	AddMember(groupID, email, addedBy string) error
	RemoveMember(groupID, email string) error
}

// GroupAuditFn records a group mutation in the audit log. May be nil.
type GroupAuditFn func(actor, action, target string)

type AdminGroupDeps struct {
	Repo  GroupStore
	Audit GroupAuditFn
}

// AdminGroupHandlers serves /api/v1/admin/groups/… (admin only; the gate is
// applied at route registration).
type AdminGroupHandlers struct {
	d AdminGroupDeps
}

func NewAdminGroupHandlers(d AdminGroupDeps) *AdminGroupHandlers {
	return &AdminGroupHandlers{d: d}
}

type groupInput struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

type memberInput struct {
	Email string `json:"email"`
}

func actorOf(r *http.Request) string {
	if s, ok := sessionFromAnyKey(r.Context()); ok {
		return s.Email
	}
	return ""
}

func (h *AdminGroupHandlers) audit(r *http.Request, action, target string) {
	if h.d.Audit != nil {
		h.d.Audit(actorOf(r), action, target)
	}
}

// writeGroupErr maps repository sentinels to HTTP codes.
func writeGroupErr(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, db.ErrGroupNotFound):
		writeJSONErr(w, http.StatusNotFound, "not_found", "unknown group")
	case errors.Is(err, db.ErrGroupNameTaken):
		writeJSONErr(w, http.StatusConflict, "name_taken", "a group with this name already exists")
	case errors.Is(err, db.ErrUnknownUser):
		writeJSONErr(w, http.StatusNotFound, "unknown_user",
			"unknown user: they must sign in once before being added to a group")
	default:
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
	}
}

func decodeGroupInput(w http.ResponseWriter, r *http.Request) (groupInput, bool) {
	var in groupInput
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&in); err != nil {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "invalid JSON body")
		return in, false
	}
	in.Name = strings.TrimSpace(in.Name)
	in.Description = strings.TrimSpace(in.Description)
	if n := utf8.RuneCountInString(in.Name); n < 1 || n > 120 {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "name must be 1..120 characters")
		return in, false
	}
	if utf8.RuneCountInString(in.Description) > 500 {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "description must be at most 500 characters")
		return in, false
	}
	return in, true
}

func groupJSON(g db.Group) map[string]interface{} {
	return map[string]interface{}{
		"id":          g.ID,
		"name":        g.Name,
		"description": g.Description,
		"created_by":  g.CreatedBy,
		"created_at":  g.CreatedAt,
		"updated_at":  g.UpdatedAt,
	}
}

// List handles GET /api/v1/admin/groups.
func (h *AdminGroupHandlers) List(w http.ResponseWriter, r *http.Request) {
	rows, err := h.d.Repo.List()
	if err != nil {
		writeGroupErr(w, err)
		return
	}
	items := make([]map[string]interface{}, 0, len(rows))
	for _, s := range rows {
		m := groupJSON(s.Group)
		m["member_count"] = s.MemberCount
		items = append(items, m)
	}
	writeTypedJSON(w, http.StatusOK, map[string]interface{}{"items": items, "total": len(items)})
}

// Create handles POST /api/v1/admin/groups.
func (h *AdminGroupHandlers) Create(w http.ResponseWriter, r *http.Request) {
	in, ok := decodeGroupInput(w, r)
	if !ok {
		return
	}
	g, err := h.d.Repo.Create(in.Name, in.Description, actorOf(r))
	if err != nil {
		writeGroupErr(w, err)
		return
	}
	h.audit(r, "group.create", g.ID)
	writeTypedJSON(w, http.StatusCreated, groupJSON(*g))
}

// Get handles GET /api/v1/admin/groups/{id}.
func (h *AdminGroupHandlers) Get(w http.ResponseWriter, r *http.Request) {
	g, members, err := h.d.Repo.Get(r.PathValue("id"))
	if err != nil {
		writeGroupErr(w, err)
		return
	}
	out := groupJSON(*g)
	ms := make([]map[string]interface{}, 0, len(members))
	for _, m := range members {
		ms = append(ms, map[string]interface{}{
			"email":        m.Email,
			"display_name": m.DisplayName,
			"is_allowed":   m.IsAllowed,
			"added_by":     m.AddedBy,
			"added_at":     m.AddedAt,
		})
	}
	out["members"] = ms
	out["member_count"] = len(ms)
	writeTypedJSON(w, http.StatusOK, out)
}

// Update handles PUT /api/v1/admin/groups/{id}.
func (h *AdminGroupHandlers) Update(w http.ResponseWriter, r *http.Request) {
	in, ok := decodeGroupInput(w, r)
	if !ok {
		return
	}
	g, err := h.d.Repo.Update(r.PathValue("id"), in.Name, in.Description)
	if err != nil {
		writeGroupErr(w, err)
		return
	}
	h.audit(r, "group.update", g.ID)
	writeTypedJSON(w, http.StatusOK, groupJSON(*g))
}

// Delete handles DELETE /api/v1/admin/groups/{id}.
func (h *AdminGroupHandlers) Delete(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if err := h.d.Repo.Delete(id); err != nil {
		writeGroupErr(w, err)
		return
	}
	h.audit(r, "group.delete", id)
	w.WriteHeader(http.StatusNoContent)
}

// AddMember handles POST /api/v1/admin/groups/{id}/members.
func (h *AdminGroupHandlers) AddMember(w http.ResponseWriter, r *http.Request) {
	var in memberInput
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4<<10)).Decode(&in); err != nil {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "invalid JSON body")
		return
	}
	email := strings.TrimSpace(in.Email)
	if email == "" || !strings.Contains(email, "@") {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "email required")
		return
	}
	id := r.PathValue("id")
	if err := h.d.Repo.AddMember(id, email, actorOf(r)); err != nil {
		writeGroupErr(w, err)
		return
	}
	h.audit(r, "group.member_add", id+" "+email)
	writeTypedJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// RemoveMember handles DELETE /api/v1/admin/groups/{id}/members/{email}.
func (h *AdminGroupHandlers) RemoveMember(w http.ResponseWriter, r *http.Request) {
	id, email := r.PathValue("id"), r.PathValue("email")
	if err := h.d.Repo.RemoveMember(id, email); err != nil {
		writeGroupErr(w, err)
		return
	}
	h.audit(r, "group.member_remove", id+" "+email)
	w.WriteHeader(http.StatusNoContent)
}

// writeTypedJSON is writeJSON plus the Content-Type header.
func writeTypedJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	writeJSON(w, code, v)
}
