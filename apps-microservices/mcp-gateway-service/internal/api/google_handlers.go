package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"
	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	goGoogle "mcp-gateway/internal/google"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/validation"
	"golang.org/x/oauth2"
)

// SetGoogleTokenRepo injects the Google token repository and OAuth client.
func (h *Handler) SetGoogleTokenRepo(repo *repository.GoogleTokenRepo, oauthClient *goGoogle.OAuthClient) {
	h.googleTokenRepo = repo
	h.googleOAuth = oauthClient
}

// ── Google Account Management ────────────────────────────────────────────────

// handleGoogleAuthURL returns the Google OAuth2 consent URL.
func (h *Handler) handleGoogleAuthURL(w http.ResponseWriter, r *http.Request) {
	if h.googleOAuth == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "Google OAuth2 not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set)"})
		return
	}

	state, err := goGoogle.GenerateState()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to generate state"})
		return
	}

	// Store state in a short-lived cookie for CSRF validation on callback
	http.SetCookie(w, &http.Cookie{
		Name:     "google_oauth_state",
		Value:    state,
		Path:     "/api/v1/google/callback",
		MaxAge:   600, // 10 minutes
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	})

	url := h.googleOAuth.BuildAuthURL(state)
	writeJSON(w, http.StatusOK, map[string]string{"url": url})
}

// handleGoogleCallback handles the Google OAuth2 callback, exchanges the code
// for tokens, stores them encrypted, and redirects to the frontend settings page.
func (h *Handler) handleGoogleCallback(w http.ResponseWriter, r *http.Request) {
	if h.googleOAuth == nil {
		http.Error(w, "Google OAuth2 not configured", http.StatusServiceUnavailable)
		return
	}

	// Validate CSRF state
	stateCookie, err := r.Cookie("google_oauth_state")
	if err != nil || stateCookie.Value == "" {
		http.Error(w, "missing state cookie", http.StatusBadRequest)
		return
	}
	if r.URL.Query().Get("state") != stateCookie.Value {
		http.Error(w, "state mismatch", http.StatusBadRequest)
		return
	}
	// Clear the state cookie
	http.SetCookie(w, &http.Cookie{
		Name:     "google_oauth_state",
		Value:    "",
		Path:     "/api/v1/google/callback",
		MaxAge:   -1,
		HttpOnly: true,
	})

	// Check for error from Google
	if errParam := r.URL.Query().Get("error"); errParam != "" {
		http.Redirect(w, r, "/settings?google=error&message="+errParam, http.StatusFound)
		return
	}

	code := r.URL.Query().Get("code")
	if code == "" {
		http.Error(w, "missing authorization code", http.StatusBadRequest)
		return
	}

	// Exchange code for tokens
	token, err := h.googleOAuth.ExchangeCode(r.Context(), code)
	if err != nil {
		log.Printf("[google] failed to exchange code: %v", err)
		http.Redirect(w, r, "/settings?google=error&message=token_exchange_failed", http.StatusFound)
		return
	}

	// Get the user's Google email using the userinfo endpoint
	client := h.googleOAuth.BuildHTTPClient(r.Context(), token)
	googleEmail, err := fetchGoogleEmail(client)
	if err != nil {
		log.Printf("[google] failed to fetch email: %v", err)
		googleEmail = "unknown"
	}

	// Find the gateway user
	email := auth.UserEmailFromContext(r.Context())
	user, err := h.userRepo.GetByEmail(email)
	if err != nil || user == nil {
		http.Error(w, "user not found", http.StatusUnauthorized)
		return
	}

	// Store or update tokens
	existing, err := h.googleTokenRepo.GetByUserID(user.ID)
	if err != nil {
		log.Printf("[google] failed to check existing token: %v", err)
		http.Redirect(w, r, "/settings?google=error&message=db_error", http.StatusFound)
		return
	}

	expiry := token.Expiry
	if existing == nil {
		// Create new record
		gt := &db.UserGoogleToken{
			UserID:       user.ID,
			Email:        googleEmail,
			AccessToken:  []byte(token.AccessToken),
			RefreshToken: []byte(token.RefreshToken),
			TokenExpiry:  &expiry,
		}
		if err := h.googleTokenRepo.Create(gt); err != nil {
			log.Printf("[google] failed to store token: %v", err)
			http.Redirect(w, r, "/settings?google=error&message=db_error", http.StatusFound)
			return
		}
	} else {
		// Update existing record
		existing.Email = googleEmail
		existing.AccessToken = []byte(token.AccessToken)
		existing.RefreshToken = []byte(token.RefreshToken)
		existing.TokenExpiry = &expiry
		if err := h.googleTokenRepo.Update(existing); err != nil {
			log.Printf("[google] failed to update token: %v", err)
			http.Redirect(w, r, "/settings?google=error&message=db_error", http.StatusFound)
			return
		}
	}

	http.Redirect(w, r, "/settings?google=connected", http.StatusFound)
}

// handleGoogleDisconnect removes stored Google tokens for the authenticated admin.
func (h *Handler) handleGoogleDisconnect(w http.ResponseWriter, r *http.Request) {
	email := auth.UserEmailFromContext(r.Context())
	user, err := h.userRepo.GetByEmail(email)
	if err != nil || user == nil {
		writeJSON(w, http.StatusUnauthorized, ErrorResponse{Error: "user not found"})
		return
	}

	if err := h.googleTokenRepo.DeleteByUserID(user.ID); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to disconnect"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"status": "disconnected"})
}

// handleGoogleStatus returns the Google connection status for the authenticated admin.
func (h *Handler) handleGoogleStatus(w http.ResponseWriter, r *http.Request) {
	email := auth.UserEmailFromContext(r.Context())
	user, err := h.userRepo.GetByEmail(email)
	if err != nil || user == nil {
		writeJSON(w, http.StatusOK, GoogleStatusResponse{Connected: false})
		return
	}

	token, err := h.googleTokenRepo.GetByUserID(user.ID)
	if err != nil || token == nil {
		writeJSON(w, http.StatusOK, GoogleStatusResponse{Connected: false})
		return
	}

	writeJSON(w, http.StatusOK, GoogleStatusResponse{Connected: true, Email: token.Email})
}

// handleListSpreadsheets lists the user's Google Spreadsheets from Drive.
func (h *Handler) handleListSpreadsheets(w http.ResponseWriter, r *http.Request) {
	client, err := h.getGoogleHTTPClient(r)
	if err != nil {
		h.writeGoogleError(w, err)
		return
	}

	query := r.URL.Query().Get("q")
	items, err := goGoogle.ListSpreadsheets(r.Context(), client, query)
	if err != nil {
		log.Printf("[google] failed to list spreadsheets: %v", err)
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "failed to list spreadsheets: " + err.Error()})
		return
	}

	resp := SpreadsheetListResponse{
		Spreadsheets: make([]SpreadsheetListItemResponse, 0, len(items)),
	}
	for _, item := range items {
		resp.Spreadsheets = append(resp.Spreadsheets, SpreadsheetListItemResponse{
			ID:           item.ID,
			Name:         item.Name,
			ModifiedTime: item.ModifiedTime,
			WebViewLink:  item.WebViewLink,
		})
	}
	writeJSON(w, http.StatusOK, resp)
}

// ── Spreadsheet Operations ──────────────────────────────────────────────────

// handleSheetInfo retrieves spreadsheet metadata (title, sheet names).
func (h *Handler) handleSheetInfo(w http.ResponseWriter, r *http.Request) {
	client, err := h.getGoogleHTTPClient(r)
	if err != nil {
		h.writeGoogleError(w, err)
		return
	}

	var req SheetInfoRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.SpreadsheetURL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "spreadsheet_url is required"})
		return
	}

	spreadsheetID, err := goGoogle.ParseSpreadsheetURL(req.SpreadsheetURL)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid spreadsheet URL"})
		return
	}

	info, err := goGoogle.GetSpreadsheetInfo(r.Context(), client, spreadsheetID)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "failed to access spreadsheet: " + err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, SheetInfoResponse{
		SpreadsheetID: info.SpreadsheetID,
		Title:         info.Title,
		Sheets:        info.Sheets,
	})
}

// handleSheetPreview returns column headers and first N rows from a sheet.
func (h *Handler) handleSheetPreview(w http.ResponseWriter, r *http.Request) {
	client, err := h.getGoogleHTTPClient(r)
	if err != nil {
		h.writeGoogleError(w, err)
		return
	}

	var req SheetPreviewRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.SpreadsheetID == "" || req.SheetName == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "spreadsheet_id and sheet_name are required"})
		return
	}

	preview, err := goGoogle.GetSheetPreview(r.Context(), client, req.SpreadsheetID, req.SheetName, 10)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "failed to read sheet: " + err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, SheetPreviewResponse{
		Headers:   preview.Headers,
		Rows:      preview.Rows,
		TotalRows: preview.TotalRows,
	})
}

// handleSheetImport reads all rows, applies column mapping, and creates MCP servers.
func (h *Handler) handleSheetImport(w http.ResponseWriter, r *http.Request) {
	client, err := h.getGoogleHTTPClient(r)
	if err != nil {
		h.writeGoogleError(w, err)
		return
	}

	var req SheetImportRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.SpreadsheetID == "" || req.SheetName == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "spreadsheet_id and sheet_name are required"})
		return
	}
	if req.ColumnMapping.Name == "" || req.ColumnMapping.URL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "column_mapping.name and column_mapping.url are required"})
		return
	}

	headers, rows, err := goGoogle.ReadAllRows(r.Context(), client, req.SpreadsheetID, req.SheetName)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "failed to read sheet: " + err.Error()})
		return
	}
	if len(rows) == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "spreadsheet has no data rows"})
		return
	}

	// Build column index: header name → column index
	colIndex := make(map[string]int, len(headers))
	for i, h := range headers {
		colIndex[h] = i
	}

	userEmail := auth.UserEmailFromContext(r.Context())
	resp := SheetImportResponse{
		Total:   len(rows),
		Results: make([]SheetImportResultEntry, 0, len(rows)),
	}

	for rowIdx, row := range rows {
		result := h.importSheetRow(r, rowIdx+2, row, colIndex, &req, userEmail) // +2: 1-based + header row
		switch result.Status {
		case "imported":
			resp.Imported++
		case "skipped":
			resp.Skipped++
		default:
			resp.Errors++
		}
		resp.Results = append(resp.Results, result)
	}

	writeJSON(w, http.StatusOK, resp)
}

// handleImportInstancesFromSheet reads every data row of a Google Sheet and
// creates one template instance per row. The template is selected once (per
// request) via TemplateSlug; the column mapping pulls the instance name,
// credentials JSON (as a single cell), and one cell per required_extra_env key.
//
// Rows are processed sequentially — each spawn takes a few seconds and the
// runner has a finite port pool, so concurrency would complicate error
// handling without a clear latency win at the target batch size (< 50 rows).
// If this becomes a bottleneck, a worker pool sized to the runner's free port
// count can be layered on top without touching the per-row logic.
func (h *Handler) handleImportInstancesFromSheet(w http.ResponseWriter, r *http.Request) {
	if h.templateRepo == nil || h.instanceRepo == nil || h.repo == nil || h.runner == nil || h.config == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}

	client, err := h.getGoogleHTTPClient(r)
	if err != nil {
		h.writeGoogleError(w, err)
		return
	}

	var req InstanceSheetImportRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.SpreadsheetID == "" || req.SheetName == "" || req.TemplateSlug == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "spreadsheet_id, sheet_name, and template_slug are required"})
		return
	}
	if req.NameColumn == "" || req.CredentialsColumn == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "name_column and credentials_column are required"})
		return
	}
	if req.FixedToolPrefix != "" && !alphanumericRe.MatchString(req.FixedToolPrefix) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "fixed_tool_prefix must contain only alphanumeric characters (a-z, A-Z, 0-9)"})
		return
	}

	tpl, err := h.templateRepo.GetBySlug(req.TemplateSlug)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "unknown template: " + req.TemplateSlug})
		return
	}
	// Only "stdio" templates spawn subprocesses — http_batch rows are a UI
	// shortcut that routes to the generic /servers/import-google flow and must
	// never be passed here. Fail fast with a descriptive 400 instead of a
	// confusing runner-side error later.
	if tpl.Kind != "" && tpl.Kind != "stdio" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: fmt.Sprintf("template %s is not an instance-creating template (kind=%s)", tpl.Slug, tpl.Kind),
		})
		return
	}

	// Every required schema field MUST be mapped before any network work. We
	// reuse the template_dto schema shape (key + required).
	schema, err := decodeRequiredExtraEnvSchema(tpl.RequiredExtraEnv)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "template schema is malformed"})
		return
	}
	for _, field := range schema {
		if !field.Required {
			continue
		}
		col, ok := req.ExtraEnvColumns[field.Key]
		if !ok || strings.TrimSpace(col) == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("extra_env_columns: mapping for %q is required", field.Key)})
			return
		}
	}

	// Pull sheet data.
	headers, rows, err := goGoogle.ReadAllRows(r.Context(), client, req.SpreadsheetID, req.SheetName)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "failed to read sheet: " + err.Error()})
		return
	}
	if len(rows) == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "spreadsheet has no data rows"})
		return
	}

	// Build header → column-index map.
	colIndex := make(map[string]int, len(headers))
	for i, h := range headers {
		colIndex[h] = i
	}

	// Every mapped column must exist in the sheet — surface this up-front
	// rather than failing N rows in a row with the same error.
	if _, ok := colIndex[req.NameColumn]; !ok {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("name_column %q not found in sheet headers", req.NameColumn)})
		return
	}
	if _, ok := colIndex[req.CredentialsColumn]; !ok {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("credentials_column %q not found in sheet headers", req.CredentialsColumn)})
		return
	}
	for key, col := range req.ExtraEnvColumns {
		if col == "" {
			continue
		}
		if _, ok := colIndex[col]; !ok {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("extra_env column %q (for key %q) not found in sheet headers", col, key)})
			return
		}
	}

	// Parse fixed tags once.
	var fixedTags []string
	if req.FixedTags != "" {
		for _, tag := range strings.Split(req.FixedTags, ",") {
			tag = strings.TrimSpace(tag)
			if tag != "" {
				fixedTags = append(fixedTags, tag)
			}
		}
	}

	createdBy := auth.UserEmailFromContext(r.Context())
	resp := SheetImportResponse{
		Total:   len(rows),
		Results: make([]SheetImportResultEntry, 0, len(rows)),
	}

	getVal := func(row []string, header string) string {
		if header == "" {
			return ""
		}
		idx, ok := colIndex[header]
		if !ok || idx >= len(row) {
			return ""
		}
		return strings.TrimSpace(row[idx])
	}

	for rowIdx, row := range rows {
		rowNum := rowIdx + 2 // 1-based + header row
		result := SheetImportResultEntry{Row: rowNum}

		rawName := getVal(row, req.NameColumn)
		if rawName == "" {
			result.Status = "error"
			result.Message = "missing required field: name"
			resp.Results = append(resp.Results, result)
			resp.Errors++
			continue
		}
		instName := rawName
		if req.NamePrefix != "" {
			instName = strings.TrimSpace(req.NamePrefix + " " + rawName)
		}
		result.Name = instName

		credsRaw := getVal(row, req.CredentialsColumn)
		if credsRaw == "" {
			result.Status = "error"
			result.Message = "missing required field: credentials"
			resp.Results = append(resp.Results, result)
			resp.Errors++
			continue
		}
		credBytes := []byte(credsRaw)
		if _, err := validation.ValidateServiceAccountJSON(credBytes); err != nil {
			result.Status = "error"
			result.Message = "invalid credentials: " + err.Error()
			resp.Results = append(resp.Results, result)
			resp.Errors++
			continue
		}

		// Build extra_env from the mapped columns.
		extraEnv := make(map[string]string, len(req.ExtraEnvColumns))
		for key, col := range req.ExtraEnvColumns {
			if v := getVal(row, col); v != "" {
				extraEnv[key] = v
			}
		}
		if err := validateExtraEnv(tpl.RequiredExtraEnv, extraEnv); err != nil {
			result.Status = "error"
			result.Message = err.Error()
			resp.Results = append(resp.Results, result)
			resp.Errors++
			continue
		}

		_, _, cerr := h.createInstanceFromSpec(
			r.Context(),
			tpl,
			instName,
			credBytes,
			extraEnv,
			fixedTags,
			req.FixedIcon,
			req.FixedToolPrefix,
			req.AutoDiscover,
			createdBy,
		)
		if cerr != nil {
			_, msg := classifyCreateInstanceError(cerr)
			result.Status = "error"
			result.Message = msg
			resp.Results = append(resp.Results, result)
			resp.Errors++
			continue
		}

		result.Status = "imported"
		resp.Results = append(resp.Results, result)
		resp.Imported++
	}

	writeJSON(w, http.StatusOK, resp)
}

// decodeRequiredExtraEnvSchema parses the template's required_extra_env
// raw JSON into a typed slice. Empty raw is a valid (no-schema) result.
func decodeRequiredExtraEnvSchema(raw json.RawMessage) ([]requiredExtraEnvField, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var schema []requiredExtraEnvField
	if err := json.Unmarshal(raw, &schema); err != nil {
		return nil, err
	}
	return schema, nil
}

type requiredExtraEnvField struct {
	Key      string `json:"key"`
	Label    string `json:"label"`
	Required bool   `json:"required"`
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// getGoogleHTTPClient builds an authenticated Google HTTP client for the current user.
func (h *Handler) getGoogleHTTPClient(r *http.Request) (*http.Client, error) {
	if h.googleOAuth == nil {
		return nil, fmt.Errorf("google_not_configured")
	}

	email := auth.UserEmailFromContext(r.Context())
	user, err := h.userRepo.GetByEmail(email)
	if err != nil || user == nil {
		return nil, fmt.Errorf("user_not_found")
	}

	gt, err := h.googleTokenRepo.GetByUserID(user.ID)
	if err != nil {
		return nil, fmt.Errorf("db_error")
	}
	if gt == nil {
		return nil, fmt.Errorf("google_not_connected")
	}

	token := &oauth2.Token{
		AccessToken:  string(gt.AccessToken),
		RefreshToken: string(gt.RefreshToken),
		TokenType:    "Bearer",
	}
	if gt.TokenExpiry != nil {
		token.Expiry = *gt.TokenExpiry
	}

	// Use a TokenSource that auto-refreshes
	ts := h.googleOAuth.TokenSource(r.Context(), token)
	newToken, err := ts.Token()
	if err != nil {
		return nil, fmt.Errorf("google_token_revoked")
	}

	// If the token was refreshed, update the DB
	if newToken.AccessToken != token.AccessToken {
		expiry := newToken.Expiry
		gt.AccessToken = []byte(newToken.AccessToken)
		gt.RefreshToken = []byte(newToken.RefreshToken)
		gt.TokenExpiry = &expiry
		_ = h.googleTokenRepo.Update(gt)
	}

	return oauth2.NewClient(r.Context(), ts), nil
}

// writeGoogleError writes an appropriate error response based on the error type.
func (h *Handler) writeGoogleError(w http.ResponseWriter, err error) {
	switch err.Error() {
	case "google_not_configured":
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "Google OAuth2 not configured"})
	case "user_not_found":
		writeJSON(w, http.StatusUnauthorized, ErrorResponse{Error: "user not found"})
	case "google_not_connected":
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "Google account not connected. Please connect in Settings."})
	case "google_token_revoked":
		writeJSON(w, http.StatusUnauthorized, ErrorResponse{Error: "Google access revoked. Please reconnect in Settings."})
	default:
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
	}
}

// importSheetRow creates a single MCP server from a spreadsheet row.
func (h *Handler) importSheetRow(r *http.Request, rowNum int, row []string, colIndex map[string]int, req *SheetImportRequest, userEmail string) SheetImportResultEntry {
	result := SheetImportResultEntry{Row: rowNum}
	mapping := &req.ColumnMapping

	getVal := func(header string) string {
		if header == "" {
			return ""
		}
		if idx, ok := colIndex[header]; ok && idx < len(row) {
			return strings.TrimSpace(row[idx])
		}
		return ""
	}

	name := getVal(mapping.Name)
	serverURL := getVal(mapping.URL)

	// Apply name prefix
	if req.NamePrefix != "" && name != "" {
		name = req.NamePrefix + name
	}

	if name == "" || serverURL == "" {
		result.Status = "error"
		result.Message = "missing required field: name or url"
		result.Name = name
		return result
	}
	result.Name = name

	// Check for duplicate URL or name
	existing, _ := h.repo.ListAll(nil, "", "")
	for _, s := range existing {
		if s.URL == strings.TrimRight(serverURL, "/") || s.Name == name {
			result.Status = "skipped"
			result.Message = fmt.Sprintf("server already exists (id: %s)", s.ID)
			return result
		}
	}

	id := uuid.New().String()
	srv := db.MCPServer{
		ID:                  id,
		Name:                name,
		URL:                 strings.TrimRight(serverURL, "/"),
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		MCPTransport:        "http",
		DocSlug:             generateDocSlug(name, id),
		CreatedBy:           userEmail,
		// TemplateSlug is non-empty only when the caller is the templates
		// catalog (e.g. custom-http). The regular /servers/import-google
		// flow leaves this empty so the imported rows show up in the docs
		// and docs-admin lists as normal servers.
		TemplateSlug: req.TemplateSlug,
	}

	// Apply optional mapped fields
	if v := getVal(mapping.TransportPreference); v != "" {
		srv.TransportPreference = v
	}
	if v := getVal(mapping.ConnectTimeoutMs); v != "" {
		if n, err := strconv.ParseUint(v, 10, 32); err == nil {
			srv.ConnectTimeoutMs = uint(n)
		}
	}
	if req.FixedToolPrefix != "" {
		srv.ToolPrefix = req.FixedToolPrefix
	} else if v := getVal(mapping.ToolPrefix); v != "" {
		srv.ToolPrefix = v
	}
	if req.FixedIcon != "" {
		srv.Icon = req.FixedIcon
	} else if v := getVal(mapping.Icon); v != "" {
		srv.Icon = v
	}
	if v := getVal(mapping.MCPTransport); v != "" {
		srv.MCPTransport = v
	}
	if v := getVal(mapping.MCPCommand); v != "" {
		srv.MCPCommand = v
	}
	if v := getVal(mapping.MCPArgs); v != "" {
		srv.MCPArgs = json.RawMessage(v)
	}
	if v := getVal(mapping.MCPEnv); v != "" {
		srv.MCPEnv = json.RawMessage(v)
	}
	if req.DisableDocumentation {
		srv.DocSlug = ""
	} else if v := getVal(mapping.DocSlug); v != "" {
		srv.DocSlug = v
	}
	if !req.DisableDocumentation {
		if v := getVal(mapping.DocDescription); v != "" {
			srv.DocDescription = v
		}
	}

	// Auth headers: expect JSON string like {"Authorization": "Bearer xxx"}
	if v := getVal(mapping.AuthHeaders); v != "" {
		srv.AuthHeaders = []byte(v)
	}

	// Tags: merge sheet column + fixed tags (deduplicated)
	tagSet := make(map[string]bool)
	if v := getVal(mapping.Tags); v != "" {
		for _, tag := range strings.Split(v, ",") {
			tag = strings.TrimSpace(tag)
			if tag != "" && !tagSet[tag] {
				tagSet[tag] = true
				srv.Tags = append(srv.Tags, db.ServerTag{ServerID: id, Tag: tag})
			}
		}
	}
	if req.FixedTags != "" {
		for _, tag := range strings.Split(req.FixedTags, ",") {
			tag = strings.TrimSpace(tag)
			if tag != "" && !tagSet[tag] {
				tagSet[tag] = true
				srv.Tags = append(srv.Tags, db.ServerTag{ServerID: id, Tag: tag})
			}
		}
	}

	if err := h.repo.Create(&srv); err != nil {
		if strings.Contains(err.Error(), "Duplicate") {
			result.Status = "skipped"
			result.Message = "duplicate URL or slug"
			return result
		}
		result.Status = "error"
		result.Message = err.Error()
		return result
	}

	result.Status = "imported"

	// Auto-discover for remote servers
	if req.AutoDiscover && srv.MCPTransport != "stdio" && serverURL != "" {
		authHeaders := parseAuthHeaders(srv.AuthHeaders)
		if err := h.gw.DiscoverAndRegister(r.Context(), id, srv.URL, authHeaders); err != nil {
			log.Printf("[google] auto-discover failed for %s (%s): %v", name, srv.URL, err)
			_ = h.repo.UpdateHealth(id, "unhealthy", err.Error())
		} else {
			if backend := h.registry.FindByID(id); backend != nil {
				h.saveBackendCapabilities(id, backend)
			}
		}
	}

	return result
}

// fetchGoogleEmail retrieves the user's email from Google's userinfo endpoint.
func fetchGoogleEmail(client *http.Client) (string, error) {
	resp, err := client.Get("https://www.googleapis.com/oauth2/v2/userinfo")
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	var info struct {
		Email string `json:"email"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		return "", err
	}
	return info.Email, nil
}

// resolveCreatedBy returns the created_by value to stamp on a row.
// Empty column header, missing header, or empty/whitespace cell all fall back
// to fallback (the connected user's email). Non-empty cells are trimmed.
//
// Kept pure and decoupled from *http.Request so both import handlers share
// one definition of the rule (see google_handlers_test.go for the contract).
func resolveCreatedBy(column string, row []string, colIndex map[string]int, fallback string) string {
	if column == "" {
		return fallback
	}
	idx, ok := colIndex[column]
	if !ok || idx >= len(row) {
		return fallback
	}
	v := strings.TrimSpace(row[idx])
	if v == "" {
		return fallback
	}
	return v
}
