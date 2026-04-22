# Google Spreadsheet Import for MCP Gateway

**Date:** 2026-04-16
**Status:** Draft
**Services:** `mcp-gateway-service` (Go), `mcp-gateway-frontend` (Vue 3)

## Problem

Admins currently import MCP servers one by one or via `.mcp.json` paste. Teams that maintain server lists in Google Spreadsheets have no way to import directly — they must manually re-enter each server. This feature adds Google Sheets as an import source with per-admin OAuth2 authentication and interactive column mapping.

## Requirements

- Each admin connects their own Google account (OAuth2) to read their spreadsheets
- Admin enters a spreadsheet URL, selects a sheet/tab, maps columns to MCP server fields
- Required fields: Server Name, Server URL. All other `CreateServerRequest` fields are optional
- Auto-discover toggle per import (consistent with existing JSON import)
- Per-admin Google credential storage (encrypted at rest)
- Settings page for managing Google account connection

## Architecture: Backend-Centric

The Go backend handles the full Google OAuth2 flow, token storage, and Sheets API calls. The Vue frontend orchestrates the UI steps and calls backend APIs.

### Google OAuth2 Flow

**Global config (env vars):**
- `GOOGLE_CLIENT_ID` — OAuth2 client ID from Google Cloud Console
- `GOOGLE_CLIENT_SECRET` — OAuth2 client secret

**Redirect URI:** Derived from the existing `GATEWAY_PUBLIC_URL` env var: `${GATEWAY_PUBLIC_URL}/api/v1/google/callback`. No separate env var needed — reuses the gateway's public URL already configured for OAuth2 metadata.

**Scope:** `https://www.googleapis.com/auth/spreadsheets.readonly` — read-only access to the admin's spreadsheets.

**Flow:**
1. Admin clicks "Connect Google Account" on the Settings page
2. Frontend opens `GET /api/v1/google/auth-url` → backend generates Google consent URL with CSRF state parameter
3. Browser redirects to Google consent screen
4. Admin grants `spreadsheets.readonly` permission
5. Google redirects to `GET /api/v1/google/callback?code=...&state=...`
6. Backend validates state, exchanges authorization code for access + refresh tokens
7. Tokens encrypted (AES-256-GCM) and stored in `user_google_tokens` table
8. Backend redirects to frontend `/settings?google=connected`

**Token lifecycle:**
- Access tokens expire after ~1 hour; backend auto-refreshes using the stored refresh token
- On refresh, the new access token is re-encrypted and updated in DB
- If the refresh token is revoked (user revokes in Google), the backend returns a clear error prompting re-connection

### Database

**New table: `user_google_tokens`**

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | CHAR(36) | PK, UUID |
| `user_id` | CHAR(36) | FK → gateway_users, UNIQUE |
| `email` | VARCHAR(255) | Google account email |
| `access_token` | BLOB | Encrypted (AES-256-GCM) |
| `refresh_token` | BLOB | Encrypted (AES-256-GCM) |
| `token_expiry` | DATETIME | Access token expiry |
| `created_at` | DATETIME | Auto |
| `updated_at` | DATETIME | Auto |

GORM auto-migration handles table creation. One-to-one relationship with `gateway_users`. Encryption reuses `internal/crypto/encrypt.go`.

### Backend API Endpoints

All endpoints require admin authentication (existing JWT middleware).

#### Google Account Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/google/auth-url` | Returns Google OAuth2 consent URL |
| `GET` | `/api/v1/google/callback` | OAuth2 callback — exchanges code for tokens, stores encrypted, redirects to frontend |
| `DELETE` | `/api/v1/google/disconnect` | Deletes stored tokens for the authenticated admin |
| `GET` | `/api/v1/google/status` | Returns `{ connected: bool, email: string }` |

#### Spreadsheet Operations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/google/sheets/info` | Body: `{ "spreadsheet_url": "..." }` → Returns spreadsheet title + list of sheet names |
| `POST` | `/api/v1/google/sheets/preview` | Body: `{ "spreadsheet_id": "...", "sheet_name": "..." }` → Returns column headers + first 10 rows |
| `POST` | `/api/v1/google/sheets/import` | Body: `{ "spreadsheet_id": "...", "sheet_name": "...", "column_mapping": {...}, "auto_discover": bool }` → Returns `ImportResult` |

#### Request/Response Types

```
// POST /api/v1/google/sheets/info
SheetInfoRequest  { spreadsheet_url: string }
SheetInfoResponse { spreadsheet_id: string, title: string, sheets: string[] }

// POST /api/v1/google/sheets/preview
SheetPreviewRequest  { spreadsheet_id: string, sheet_name: string }
SheetPreviewResponse { headers: string[], rows: string[][], total_rows: int }

// POST /api/v1/google/sheets/import
SheetImportRequest {
    spreadsheet_id:  string
    sheet_name:      string
    auto_discover:   bool
    column_mapping: {
        name:                 string   // Column header (required)
        url:                  string   // Column header (required)
        auth_headers:         string   // Column header → expects JSON string
        tags:                 string   // Column header → expects comma-separated
        transport_preference: string
        connect_timeout_ms:   string
        tool_prefix:          string
        icon:                 string
        mcp_transport:        string
        mcp_command:          string
        mcp_args:             string   // Column header → expects JSON array string
        mcp_env:              string   // Column header → expects JSON object string
        doc_slug:             string
        doc_description:      string
    }
}
SheetImportResponse {
    total:    int
    imported: int
    skipped:  int
    errors:   int
    results: [{
        row:     int
        name:    string
        status:  "imported" | "skipped" | "error"
        message: string
    }]
}
```

### Backend Package Structure

```
internal/
  google/
    oauth.go      # BuildAuthURL(), ExchangeCode(), RefreshToken(), BuildClient()
    sheets.go     # GetSpreadsheetInfo(), GetSheetPreview(), ReadAllRows()
  repository/
    google_token_repo.go  # Create, GetByUserID, Update, Delete
  api/
    google_handlers.go    # HTTP handlers for /api/v1/google/*
    google_dto.go         # Request/response DTOs
  db/
    models.go             # Add UserGoogleToken model (GORM)
```

**Key implementation details:**
- `google/oauth.go` uses `golang.org/x/oauth2/google` for OAuth2 config
- `google/sheets.go` uses `google.golang.org/api/sheets/v4` for Sheets API
- Each Sheets API call creates a fresh HTTP client from the admin's decrypted tokens
- Auto-refresh: if access token expired, refresh transparently and update DB
- Spreadsheet URL parsing: extract spreadsheet ID from URLs like `https://docs.google.com/spreadsheets/d/{ID}/...`

### Frontend Architecture

**New files:**

```
src/
  api/google.ts                              # API client for /api/v1/google/*
  types/google.ts                            # TypeScript types
  views/SettingsView.vue                     # /settings page
  components/google/
    GoogleConnectCard.vue                    # Connect/disconnect card
    GoogleSheetsImportModal.vue              # Multi-step import modal
    ColumnMappingTable.vue                   # Column-to-field mapping UI
    SheetPreview.vue                         # Data preview table
```

**Router:**
- Add `/settings` route — requires auth, min role `admin`, renders `SettingsView.vue`
- Add "Settings" link to sidebar (gear icon) for admin users

**Settings Page (`SettingsView.vue`):**
- "Connected Accounts" section with `GoogleConnectCard`
- Shows Google email if connected, "Not connected" otherwise
- "Connect" button → navigates to auth URL
- "Disconnect" button → calls DELETE endpoint with confirmation

**Import Modal (`GoogleSheetsImportModal.vue`):**
- Triggered from servers view — new "Google Sheets" tab/button alongside existing "JSON" import
- If admin hasn't connected Google → shows message with link to `/settings`
- Multi-step flow:
  1. **URL Input:** Text field for spreadsheet URL + "Load" button
  2. **Sheet + Mapping:** Dropdown to select sheet tab, preview table, column mapping dropdowns
  3. **Results:** Import results (same format as existing JSON import)

**Column Mapping (`ColumnMappingTable.vue`):**
- Table with two columns: "MCP Server Field" and "Spreadsheet Column"
- Each field row has a dropdown populated with spreadsheet column headers
- Required fields (Name, URL) marked with asterisk
- Auto-detection: if a column header fuzzy-matches a field name, pre-select it
- Fuzzy matching rules: lowercase + strip spaces/underscores (e.g., "Server Name" → "servername" matches "name")

### Error Handling

| Scenario | Backend Response | Frontend Display |
|----------|-----------------|------------------|
| Google not connected | 400 `google_not_connected` | "Connect your Google account in Settings" with link |
| Spreadsheet not found / no access | 404 | "Spreadsheet not found or you don't have access" |
| Invalid spreadsheet URL | 400 | "Invalid Google Spreadsheet URL" |
| Google token revoked | 401 `google_token_revoked` | "Google access revoked. Please reconnect in Settings" |
| Google API rate limit | 429 | "Google API rate limit reached. Try again later" |
| Missing required columns (name/url) in mapping | 400 | Highlighted missing fields in mapping UI |
| Row-level parse errors | 200 with per-row errors | Per-row error messages in results table |
| Empty spreadsheet | 400 | "Spreadsheet is empty or has no data rows" |

### Security

- Refresh tokens encrypted at rest using existing AES-256-GCM (`ENCRYPTION_KEY`)
- OAuth2 state parameter prevents CSRF during consent flow
- Minimal Google scope: `spreadsheets.readonly` only
- No Google credentials stored in code or env beyond client ID/secret
- Each admin can only access their own Google account's spreadsheets
- Disconnect fully removes tokens from DB (not just soft-delete)
- Auth headers from spreadsheet cells are encrypted before storage (reuses existing server creation logic)

### Audit Logging

New audit events using existing `audit_repo.go`:
- `google_account_connected` — admin connected Google account
- `google_account_disconnected` — admin disconnected
- `google_sheets_import` — admin imported servers (with spreadsheet ID, sheet name, result counts)

## Verification

1. **Google OAuth2 flow:** Connect Google account → verify token stored → disconnect → verify token deleted
2. **Spreadsheet access:** Load a real spreadsheet URL → verify title and sheet names returned
3. **Preview:** Select a sheet → verify headers and rows match spreadsheet content
4. **Column mapping:** Map columns → verify auto-detection works for matching headers
5. **Import:** Import servers → verify servers created in DB with correct field values
6. **Auto-discover:** Import with auto-discover enabled → verify tools/resources fetched
7. **Error cases:** Try invalid URL, no-access sheet, empty sheet, missing required columns
8. **Token refresh:** Wait for token expiry → verify next API call auto-refreshes
9. **Multi-admin:** Two admins connect different Google accounts → verify each sees only their sheets
10. **Build:** `docker compose build mcp-gateway-service mcp-gateway-frontend` succeeds
