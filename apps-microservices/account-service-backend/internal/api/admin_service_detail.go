package api

import (
	"encoding/json"
	"net/http"
)

type WebhookTester interface {
	TestWebhook(url, secret string) (status int, err error)
}

type AdminServiceDetailDeps struct {
	Repo    ServiceRepo
	Encrypt EncryptFunc
	Tester  WebhookTester
}

type adminServiceDetailHandler struct {
	deps AdminServiceDetailDeps
}

func NewAdminServiceDetailHandler(d AdminServiceDetailDeps) http.Handler {
	return &adminServiceDetailHandler{deps: d}
}

func (h *adminServiceDetailHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	op := r.PathValue("op")
	switch r.Method {
	case http.MethodGet:
		h.get(w, id)
	case http.MethodPut:
		h.update(w, r, id)
	case http.MethodDelete:
		h.delete(w, id)
	case http.MethodPost:
		switch op {
		case "rotate-secret":
			h.rotate(w, id)
		case "test-webhook":
			h.testWebhook(w, id)
		default:
			writeJSONErr(w, http.StatusBadRequest, "invalid_request", "unknown op")
		}
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *adminServiceDetailHandler) get(w http.ResponseWriter, id string) {
	c, err := h.deps.Repo.GetByID(id)
	if err != nil {
		writeJSONErr(w, http.StatusNotFound, "not_found", "client not found")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(redactClient(*c))
}

func (h *adminServiceDetailHandler) update(w http.ResponseWriter, r *http.Request, id string) {
	var fields map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&fields); err != nil {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	delete(fields, "id")
	delete(fields, "client_id")
	delete(fields, "client_secret_enc")
	for _, key := range []string{"redirect_uris", "allowed_roles", "claim_mappings"} {
		if v, ok := fields[key]; ok && v != nil {
			b, _ := json.Marshal(v)
			fields[key] = string(b)
		}
	}
	rename := map[string]string{
		"token_ttl_s":   "token_ttl_seconds",
		"refresh_ttl_s": "refresh_ttl_seconds",
	}
	for jsonKey, col := range rename {
		if v, ok := fields[jsonKey]; ok {
			fields[col] = v
			delete(fields, jsonKey)
		}
	}
	if err := h.deps.Repo.Update(id, fields); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	c, _ := h.deps.Repo.GetByID(id)
	w.Header().Set("Content-Type", "application/json")
	if c != nil {
		_ = json.NewEncoder(w).Encode(redactClient(*c))
	} else {
		w.WriteHeader(http.StatusNoContent)
	}
}

func (h *adminServiceDetailHandler) delete(w http.ResponseWriter, id string) {
	if err := h.deps.Repo.Delete(id); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *adminServiceDetailHandler) rotate(w http.ResponseWriter, id string) {
	secret := randB64(32)
	enc, err := h.deps.Encrypt([]byte(secret))
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "encrypt failed")
		return
	}
	if err := h.deps.Repo.Update(id, map[string]interface{}{"client_secret_enc": enc}); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"client_secret": secret})
}

func (h *adminServiceDetailHandler) testWebhook(w http.ResponseWriter, id string) {
	c, err := h.deps.Repo.GetByID(id)
	if err != nil {
		writeJSONErr(w, http.StatusNotFound, "not_found", "client not found")
		return
	}
	if c.LogoutWebhookURL == "" {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "no webhook configured")
		return
	}
	if h.deps.Tester == nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "no tester wired")
		return
	}
	status, err := h.deps.Tester.TestWebhook(c.LogoutWebhookURL, "")
	if err != nil {
		writeJSONErr(w, http.StatusBadGateway, "webhook_failed", err.Error())
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{"status": status})
}
