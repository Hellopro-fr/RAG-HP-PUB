package api

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"

	"account-service/internal/db"
)

type ServiceRepo interface {
	Create(c *db.OAuth2Client) error
	GetByID(id string) (*db.OAuth2Client, error)
	GetByClientID(id string) (*db.OAuth2Client, error)
	Update(id string, fields map[string]interface{}) error
	Delete(id string) error
	List(limit, offset int) ([]db.OAuth2Client, int64, error)
}

type EncryptFunc func([]byte) ([]byte, error)

type AdminServiceDeps struct {
	Repo    ServiceRepo
	Encrypt EncryptFunc
}

type adminServiceHandler struct {
	deps AdminServiceDeps
}

func NewAdminServiceHandler(d AdminServiceDeps) http.Handler {
	return &adminServiceHandler{deps: d}
}

func (h *adminServiceHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.list(w, r)
	case http.MethodPost:
		h.create(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *adminServiceHandler) list(w http.ResponseWriter, r *http.Request) {
	limit := parseIntParam(r, "limit", 20, 100)
	offset := parseIntParam(r, "offset", 0, 100000)
	clients, total, err := h.deps.Repo.List(limit, offset)
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	out := make([]map[string]interface{}, 0, len(clients))
	for _, c := range clients {
		out = append(out, redactClient(c))
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"items": out, "total": total, "limit": limit, "offset": offset,
	})
}

type createServiceReq struct {
	Name              string            `json:"name"`
	Description       string            `json:"description,omitempty"`
	LogoURL           string            `json:"logo_url,omitempty"`
	BrandColor        string            `json:"brand_color,omitempty"`
	RedirectURIs      []string          `json:"redirect_uris"`
	AllowedRoles      []string          `json:"allowed_roles,omitempty"`
	LogoutWebhookURL  string            `json:"logout_webhook_url,omitempty"`
	TokenTTLSeconds   int               `json:"token_ttl_s,omitempty"`
	RefreshTTLSeconds int               `json:"refresh_ttl_s,omitempty"`
	ClaimMappings     map[string]string `json:"claim_mappings,omitempty"`
	Scope             string            `json:"scope,omitempty"`
}

func (h *adminServiceHandler) create(w http.ResponseWriter, r *http.Request) {
	var req createServiceReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	if req.Name == "" || len(req.RedirectURIs) == 0 {
		writeJSONErr(w, http.StatusBadRequest, "invalid_request", "name and redirect_uris required")
		return
	}
	clientID := randB64(24)
	secret := randB64(32)
	enc, err := h.deps.Encrypt([]byte(secret))
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "encrypt failed")
		return
	}
	urisJSON, _ := json.Marshal(req.RedirectURIs)
	urisStr := string(urisJSON)
	rolesStr := ""
	if len(req.AllowedRoles) > 0 {
		b, _ := json.Marshal(req.AllowedRoles)
		rolesStr = string(b)
	}
	claimStr := ""
	if len(req.ClaimMappings) > 0 {
		b, _ := json.Marshal(req.ClaimMappings)
		claimStr = string(b)
	}
	ttl := req.TokenTTLSeconds
	if ttl == 0 {
		ttl = 60
	}
	rttl := req.RefreshTTLSeconds
	if rttl == 0 {
		rttl = 2592000
	}
	c := &db.OAuth2Client{
		ClientID:          clientID,
		ClientSecretEnc:   enc,
		Name:              req.Name,
		Description:       req.Description,
		LogoURL:           req.LogoURL,
		BrandColor:        req.BrandColor,
		RedirectURIs:      &urisStr,
		AllowedRoles:      ifNonEmpty(rolesStr),
		LogoutWebhookURL:  req.LogoutWebhookURL,
		TokenTTLSeconds:   ttl,
		RefreshTTLSeconds: rttl,
		ClaimMappings:     ifNonEmpty(claimStr),
		Scope:             req.Scope,
		IsActive:          true,
	}
	if err := h.deps.Repo.Create(c); err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", "create failed")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"id":            c.ID,
		"client_id":     clientID,
		"client_secret": secret,
		"name":          c.Name,
		"redirect_uris": req.RedirectURIs,
	})
}

func redactClient(c db.OAuth2Client) map[string]interface{} {
	return map[string]interface{}{
		"id":                 c.ID,
		"client_id":          c.ClientID,
		"name":               c.Name,
		"description":        c.Description,
		"logo_url":           c.LogoURL,
		"brand_color":        c.BrandColor,
		"redirect_uris":      jsonRaw(c.RedirectURIs),
		"allowed_roles":      jsonRaw(c.AllowedRoles),
		"logout_webhook_url": c.LogoutWebhookURL,
		"token_ttl_s":        c.TokenTTLSeconds,
		"refresh_ttl_s":      c.RefreshTTLSeconds,
		"claim_mappings":     jsonRaw(c.ClaimMappings),
		"scope":              c.Scope,
		"is_active":          c.IsActive,
		"created_at":         c.CreatedAt,
		"updated_at":         c.UpdatedAt,
	}
}

func jsonRaw(s *string) interface{} {
	if s == nil || *s == "" {
		return nil
	}
	var any interface{}
	_ = json.Unmarshal([]byte(*s), &any)
	return any
}

func ifNonEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func parseIntParam(r *http.Request, key string, def, max int) int {
	v := r.URL.Query().Get(key)
	if v == "" {
		return def
	}
	n := 0
	for _, ch := range v {
		if ch < '0' || ch > '9' {
			return def
		}
		n = n*10 + int(ch-'0')
		if n > max {
			return max
		}
	}
	if n == 0 {
		return def
	}
	return n
}

func randB64(n int) string {
	buf := make([]byte, n)
	_, _ = io.ReadFull(rand.Reader, buf)
	return base64.RawURLEncoding.EncodeToString(buf)
}

func writeJSONErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": desc,
	})
}
