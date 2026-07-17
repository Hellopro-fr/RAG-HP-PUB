package api

import (
	"crypto/subtle"
	"encoding/json"
	"log"
	"net/http"
	"strings"

	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/runnerclient"
)

type runnerSyncResponse struct {
	DesiredInstances []runnerclient.SpawnRequest `json:"desired_instances"`
}

// handleRunnerSync is called by the runner on boot and reconcile.
// Auth: X-Admin-Token only (no JWT — runner is not a user).
// Returns the full list of desired instances, with decrypted credentials so
// the runner can spawn/respawn them.
func (h *Handler) handleRunnerSync(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	if h.config == nil || h.instanceRepo == nil || h.templateRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	expected := h.config.GoogleTemplatesRunnerAdminToken
	got := r.Header.Get("X-Admin-Token")
	if expected == "" || subtle.ConstantTimeCompare([]byte(got), []byte(expected)) != 1 {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}
	// Runner sync is a machine-to-machine call; it must see every instance
	// regardless of creator (pass "" to bypass the user filter).
	instances, err := h.instanceRepo.ListAll("")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	out := runnerSyncResponse{DesiredInstances: make([]runnerclient.SpawnRequest, 0, len(instances))}
	for _, inst := range instances {
		_, plain, err := h.instanceRepo.GetByIDWithCredentials(inst.ID)
		if err != nil {
			log.Printf("[templates][WARN] runner/sync: decrypt failed for %s: %v", inst.ID, err)
			continue
		}
		tpl, err := h.templateRepo.GetBySlug(inst.TemplateSlug)
		if err != nil {
			log.Printf("[templates][WARN] runner/sync: template %s missing for instance %s", inst.TemplateSlug, inst.ID)
			continue
		}
		// Always send an empty slice (not nil) — Pydantic's list[str] on the
		// runner side rejects null with 422.
		stdioArgs := []string{}
		if len(tpl.StdioArgs) > 0 {
			_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
			if stdioArgs == nil {
				stdioArgs = []string{}
			}
		}
		var extraEnv map[string]string
		if len(inst.ExtraEnv) > 0 {
			_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
		}
		// Preferred port hint — pass the last-known port so the runner can try
		// to reallocate the same one after restart. Without this, the pool
		// hands out ports in a different order each boot (asyncio.gather is
		// non-deterministic), and mcp_servers.url ends up pointing at the
		// wrong port until the gateway rediscovers.
		out.DesiredInstances = append(out.DesiredInstances, runnerclient.SpawnRequest{
			InstanceID:      inst.ID,
			TemplateSlug:    inst.TemplateSlug,
			StdioCommand:    tpl.StdioCommand,
			StdioArgs:       stdioArgs,
			Env:             renderEnv(tpl.DefaultEnv, extraEnv, inst.ID),
			CredentialsJSON: string(plain),
			CredentialsHash: inst.CredentialsHash,
			RunnerPort:      inst.RunnerPort,
		})
	}
	writeJSON(w, http.StatusOK, out)
}

type syncUserEntry struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

type syncUsersRequest struct {
	Users []syncUserEntry `json:"users"`
}

type syncUsersResponse struct {
	Created []string `json:"created"`
	Skipped []string `json:"skipped"`
}

// handleUserSync is called by account-service-backend to pre-provision its
// users as gateway users (role config-only, is_allowed=false). Existing
// users are skipped untouched.
// Auth: X-Admin-Token only (no JWT — machine-to-machine), validated against
// ACCOUNT_INTERNAL_TOKEN, the same shared secret the gateway presents to
// account-service /internal/credentials.
func (h *Handler) handleUserSync(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	if h.config == nil || h.userRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "user sync not configured"})
		return
	}
	expected := h.config.AccountInternalToken
	got := r.Header.Get("X-Admin-Token")
	if expected == "" || subtle.ConstantTimeCompare([]byte(got), []byte(expected)) != 1 {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}
	var req syncUsersRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}
	inputs := make([]repository.SyncUserInput, 0, len(req.Users))
	for _, u := range req.Users {
		email := strings.ToLower(strings.TrimSpace(u.Email))
		if email == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "entry with empty email"})
			return
		}
		inputs = append(inputs, repository.SyncUserInput{Email: email, DisplayName: u.DisplayName})
	}
	created, skipped, err := h.userRepo.SyncUsers(inputs)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, syncUsersResponse{Created: created, Skipped: skipped})
}
