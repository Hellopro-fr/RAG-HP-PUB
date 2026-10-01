package api

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"strings"

	"mcp-gateway/internal/db"
)

// ── Admin: Executors ───────────────────────────────────────────────

func (h *Handler) handleExecutors(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		executors, err := h.installGuideRepo.ListExecutors(false)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list executors"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{"executors": executors, "total": len(executors)})
	case http.MethodPost:
		var req CreateExecutorRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
			return
		}
		if req.Slug == "" || req.Label == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "slug and label are required"})
			return
		}
		isActive := true
		if req.IsActive != nil {
			isActive = *req.IsActive
		}
		e := db.InstallExecutor{
			Slug:         req.Slug,
			Label:        decodeEntitiesString(req.Label),
			Sub:          decodeEntitiesString(req.Sub),
			Description:  decodeEntitiesString(req.Description),
			Intro:        decodeEntitiesString(req.Intro),
			Icon:         req.Icon,
			Color:        req.Color,
			Install:      req.Install,
			Verify:       req.Verify,
			McpConfig:    req.McpConfig,
			CliAddCmd:    req.CliAddCmd,
			NoteLabel:    decodeEntitiesString(req.NoteLabel),
			NoteText:     decodeEntitiesString(req.NoteText),
			NoteClass:    req.NoteClass,
			Content:      decodeEntitiesJSON(req.Content),
			DisplayOrder: req.DisplayOrder,
			IsActive:     isActive,
		}
		if err := h.installGuideRepo.CreateExecutor(&e); err != nil {
			if strings.Contains(err.Error(), "Duplicate") {
				writeJSON(w, http.StatusConflict, ErrorResponse{Error: "slug '" + req.Slug + "' already exists"})
				return
			}
			log.Printf("[api] create executor error: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to create executor"})
			return
		}
		writeJSON(w, http.StatusCreated, e)
	default:
		w.Header().Set("Allow", "GET, POST")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

func (h *Handler) handleExecutorByID(w http.ResponseWriter, r *http.Request) {
	idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/install-guides/executors/")
	idStr = strings.TrimSuffix(idStr, "/")
	id, err := strconv.ParseUint(idStr, 10, 64)
	if err != nil || id == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid executor id"})
		return
	}

	switch r.Method {
	case http.MethodGet:
		e, err := h.installGuideRepo.GetExecutor(id)
		if err != nil {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "executor not found"})
			return
		}
		writeJSON(w, http.StatusOK, e)
	case http.MethodPut:
		var req UpdateExecutorRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
			return
		}
		updates := map[string]interface{}{}
		if req.Slug != nil {
			updates["slug"] = *req.Slug
		}
		if req.Label != nil {
			updates["label"] = decodeEntitiesString(*req.Label)
		}
		if req.Sub != nil {
			updates["sub"] = decodeEntitiesString(*req.Sub)
		}
		if req.Description != nil {
			updates["description"] = decodeEntitiesString(*req.Description)
		}
		if req.Intro != nil {
			updates["intro"] = decodeEntitiesString(*req.Intro)
		}
		if req.Icon != nil {
			updates["icon"] = *req.Icon
		}
		if req.Color != nil {
			updates["color"] = *req.Color
		}
		if req.Install != nil {
			updates["install"] = *req.Install
		}
		if req.Verify != nil {
			updates["verify"] = *req.Verify
		}
		if req.McpConfig != nil {
			updates["mcp_config"] = *req.McpConfig
		}
		if req.CliAddCmd != nil {
			updates["cli_add_cmd"] = *req.CliAddCmd
		}
		if req.NoteLabel != nil {
			updates["note_label"] = decodeEntitiesString(*req.NoteLabel)
		}
		if req.NoteText != nil {
			updates["note_text"] = decodeEntitiesString(*req.NoteText)
		}
		if req.NoteClass != nil {
			updates["note_class"] = *req.NoteClass
		}
		if req.Content != nil {
			updates["content"] = decodeEntitiesJSON(*req.Content)
		}
		if req.DisplayOrder != nil {
			updates["display_order"] = *req.DisplayOrder
		}
		if req.IsActive != nil {
			updates["is_active"] = *req.IsActive
		}
		if len(updates) == 0 {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "no fields to update"})
			return
		}
		if err := h.installGuideRepo.UpdateExecutor(id, updates); err != nil {
			log.Printf("[api] update executor error: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to update executor"})
			return
		}
		e, _ := h.installGuideRepo.GetExecutor(id)
		writeJSON(w, http.StatusOK, e)
	case http.MethodDelete:
		if err := h.installGuideRepo.DeleteExecutor(id); err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to delete executor"})
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		w.Header().Set("Allow", "GET, PUT, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

// ── Admin: Configs ─────────────────────────────────────────────────

func (h *Handler) handleConfigs(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		configs, err := h.installGuideRepo.ListConfigs(false)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list configs"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{"configs": configs, "total": len(configs)})
	case http.MethodPost:
		var req CreateConfigRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
			return
		}
		if req.Slug == "" || req.Label == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "slug and label are required"})
			return
		}
		isActive := true
		if req.IsActive != nil {
			isActive = *req.IsActive
		}
		c := db.InstallConfig{
			Slug:         req.Slug,
			Label:        decodeEntitiesString(req.Label),
			Description:  decodeEntitiesString(req.Description),
			Icon:         req.Icon,
			Color:        req.Color,
			Content:      decodeEntitiesJSON(req.Content),
			DisplayOrder: req.DisplayOrder,
			IsActive:     isActive,
		}
		if err := h.installGuideRepo.CreateConfig(&c); err != nil {
			if strings.Contains(err.Error(), "Duplicate") {
				writeJSON(w, http.StatusConflict, ErrorResponse{Error: "slug '" + req.Slug + "' already exists"})
				return
			}
			log.Printf("[api] create config error: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to create config"})
			return
		}
		writeJSON(w, http.StatusCreated, c)
	default:
		w.Header().Set("Allow", "GET, POST")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

func (h *Handler) handleConfigByID(w http.ResponseWriter, r *http.Request) {
	idStr := strings.TrimPrefix(r.URL.Path, "/api/v1/install-guides/configs/")
	idStr = strings.TrimSuffix(idStr, "/")
	id, err := strconv.ParseUint(idStr, 10, 64)
	if err != nil || id == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid config id"})
		return
	}

	switch r.Method {
	case http.MethodGet:
		c, err := h.installGuideRepo.GetConfig(id)
		if err != nil {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "config not found"})
			return
		}
		writeJSON(w, http.StatusOK, c)
	case http.MethodPut:
		var req UpdateConfigRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
			return
		}
		updates := map[string]interface{}{}
		if req.Slug != nil {
			updates["slug"] = *req.Slug
		}
		if req.Label != nil {
			updates["label"] = decodeEntitiesString(*req.Label)
		}
		if req.Description != nil {
			updates["description"] = decodeEntitiesString(*req.Description)
		}
		if req.Icon != nil {
			updates["icon"] = *req.Icon
		}
		if req.Color != nil {
			updates["color"] = *req.Color
		}
		if req.Content != nil {
			updates["content"] = decodeEntitiesJSON(*req.Content)
		}
		if req.DisplayOrder != nil {
			updates["display_order"] = *req.DisplayOrder
		}
		if req.IsActive != nil {
			updates["is_active"] = *req.IsActive
		}
		if len(updates) == 0 {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "no fields to update"})
			return
		}
		if err := h.installGuideRepo.UpdateConfig(id, updates); err != nil {
			log.Printf("[api] update config error: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to update config"})
			return
		}
		c, _ := h.installGuideRepo.GetConfig(id)
		writeJSON(w, http.StatusOK, c)
	case http.MethodDelete:
		if err := h.installGuideRepo.DeleteConfig(id); err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to delete config"})
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		w.Header().Set("Allow", "GET, PUT, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

// ── Public endpoints ───────────────────────────────────────────────

func (h *Handler) handlePublicExecutors(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	executors, err := h.installGuideRepo.ListExecutors(true)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list executors"})
		return
	}
	writeJSON(w, http.StatusOK, executors)
}

func (h *Handler) handlePublicConfigs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	configs, err := h.installGuideRepo.ListConfigs(true)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list configs"})
		return
	}
	writeJSON(w, http.StatusOK, configs)
}

func (h *Handler) handlePublicConfigBySlug(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	slug := strings.TrimPrefix(r.URL.Path, "/api/v1/public/install-guides/configs/")
	slug = strings.TrimSuffix(slug, "/")
	if slug == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "slug required"})
		return
	}
	c, err := h.installGuideRepo.GetConfigBySlug(slug)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "config not found"})
		return
	}
	writeJSON(w, http.StatusOK, c)
}

func (h *Handler) handlePublicExecutorBySlug(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	slug := strings.TrimPrefix(r.URL.Path, "/api/v1/public/install-guides/executors/")
	slug = strings.TrimSuffix(slug, "/")
	if slug == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "slug required"})
		return
	}
	e, err := h.installGuideRepo.GetExecutorBySlug(slug)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "executor not found"})
		return
	}
	writeJSON(w, http.StatusOK, e)
}
