package api

import (
	"crypto/subtle"
	"net/http"

	"account-service/internal/db"
)

// DirectorySource lists every user, group and membership.
type DirectorySource interface {
	Directory() ([]db.User, []db.Group, []db.GroupMember, error)
}

type InternalDirectoryDeps struct {
	Repo       DirectorySource
	AdminToken string
}

// NewInternalDirectoryHandler exposes
//
//	GET /internal/directory
//
// gated by `X-Admin-Token` (same shared token as /internal/credentials).
// Apps that delegate login here (agent task board) read users and groups
// from it to resolve their own team permissions. Blocked users are listed
// with is_allowed=false so callers can refuse them.
func NewInternalDirectoryHandler(d InternalDirectoryDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		presented := r.Header.Get("X-Admin-Token")
		if d.AdminToken == "" ||
			subtle.ConstantTimeCompare([]byte(presented), []byte(d.AdminToken)) != 1 {
			writeJSONErr(w, http.StatusUnauthorized, "unauthorized", "missing or invalid X-Admin-Token")
			return
		}
		users, groups, members, err := d.Repo.Directory()
		if err != nil {
			writeJSONErr(w, http.StatusInternalServerError, "server_error", "directory unavailable")
			return
		}
		byGroup := make(map[string][]string, len(groups))
		for _, m := range members {
			byGroup[m.GroupID] = append(byGroup[m.GroupID], m.UserEmail)
		}
		outUsers := make([]map[string]interface{}, 0, len(users))
		for _, u := range users {
			outUsers = append(outUsers, map[string]interface{}{
				"email":        u.Email,
				"display_name": u.DisplayName,
				"is_allowed":   u.IsAllowed,
			})
		}
		outGroups := make([]map[string]interface{}, 0, len(groups))
		for _, g := range groups {
			ms := byGroup[g.ID]
			if ms == nil {
				ms = []string{}
			}
			outGroups = append(outGroups, map[string]interface{}{
				"id":          g.ID,
				"name":        g.Name,
				"description": g.Description,
				"members":     ms,
			})
		}
		writeTypedJSON(w, http.StatusOK, map[string]interface{}{
			"users":  outUsers,
			"groups": outGroups,
		})
	})
}
