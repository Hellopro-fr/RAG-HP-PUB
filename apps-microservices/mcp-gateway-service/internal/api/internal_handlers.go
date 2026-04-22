package api

import (
	"crypto/subtle"
	"encoding/json"
	"log"
	"net/http"

	"github.com/hellopro/mcp-gateway/internal/runnerclient"
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
	instances, err := h.instanceRepo.ListAll()
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
		var stdioArgs []string
		if len(tpl.StdioArgs) > 0 {
			_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
		}
		var extraEnv map[string]string
		if len(inst.ExtraEnv) > 0 {
			_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
		}
		out.DesiredInstances = append(out.DesiredInstances, runnerclient.SpawnRequest{
			InstanceID:      inst.ID,
			TemplateSlug:    inst.TemplateSlug,
			StdioCommand:    tpl.StdioCommand,
			StdioArgs:       stdioArgs,
			Env:             renderEnv(tpl.DefaultEnv, extraEnv, inst.ID),
			CredentialsJSON: string(plain),
			CredentialsHash: inst.CredentialsHash,
		})
	}
	writeJSON(w, http.StatusOK, out)
}
