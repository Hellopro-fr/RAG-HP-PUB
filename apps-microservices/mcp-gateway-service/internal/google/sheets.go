package google

import (
	"context"
	"fmt"
	"net/http"
	"regexp"

	drive "google.golang.org/api/drive/v3"
	sheets "google.golang.org/api/sheets/v4"
	"google.golang.org/api/option"
)

// SpreadsheetListItem represents a spreadsheet in the user's Google Drive.
type SpreadsheetListItem struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	ModifiedTime string `json:"modified_time"`
	WebViewLink  string `json:"web_view_link"`
}

// ListSpreadsheets lists the user's Google Spreadsheets from Drive.
func ListSpreadsheets(ctx context.Context, client *http.Client, query string) ([]SpreadsheetListItem, error) {
	srv, err := drive.NewService(ctx, option.WithHTTPClient(client))
	if err != nil {
		return nil, fmt.Errorf("create drive service: %w", err)
	}

	q := "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
	if query != "" {
		q += " and name contains '" + query + "'"
	}

	resp, err := srv.Files.List().
		Q(q).
		Fields("files(id,name,modifiedTime,webViewLink)").
		OrderBy("modifiedTime desc").
		PageSize(50).
		Context(ctx).
		Do()
	if err != nil {
		return nil, fmt.Errorf("list spreadsheets: %w", err)
	}

	items := make([]SpreadsheetListItem, 0, len(resp.Files))
	for _, f := range resp.Files {
		items = append(items, SpreadsheetListItem{
			ID:           f.Id,
			Name:         f.Name,
			ModifiedTime: f.ModifiedTime,
			WebViewLink:  f.WebViewLink,
		})
	}
	return items, nil
}

// SheetInfo holds metadata about a Google Spreadsheet.
type SheetInfo struct {
	SpreadsheetID string   `json:"spreadsheet_id"`
	Title         string   `json:"title"`
	Sheets        []string `json:"sheets"`
}

// SheetPreview holds a preview of rows from a sheet.
type SheetPreview struct {
	Headers   []string   `json:"headers"`
	Rows      [][]string `json:"rows"`
	TotalRows int        `json:"total_rows"`
}

// spreadsheetIDRegex extracts the spreadsheet ID from a Google Sheets URL.
var spreadsheetIDRegex = regexp.MustCompile(`/spreadsheets/d/([a-zA-Z0-9_-]+)`)

// ParseSpreadsheetURL extracts the spreadsheet ID from a Google Sheets URL or returns the input as-is if it looks like a bare ID.
func ParseSpreadsheetURL(urlOrID string) (string, error) {
	// Try to extract from URL
	matches := spreadsheetIDRegex.FindStringSubmatch(urlOrID)
	if len(matches) >= 2 {
		return matches[1], nil
	}
	// Might be a bare spreadsheet ID (alphanumeric + hyphens + underscores)
	if regexp.MustCompile(`^[a-zA-Z0-9_-]+$`).MatchString(urlOrID) {
		return urlOrID, nil
	}
	return "", fmt.Errorf("invalid Google Spreadsheet URL or ID")
}

// GetSpreadsheetInfo retrieves the title and sheet names from a spreadsheet.
func GetSpreadsheetInfo(ctx context.Context, client *http.Client, spreadsheetID string) (*SheetInfo, error) {
	srv, err := sheets.NewService(ctx, option.WithHTTPClient(client))
	if err != nil {
		return nil, fmt.Errorf("create sheets service: %w", err)
	}

	sp, err := srv.Spreadsheets.Get(spreadsheetID).Fields("properties.title,sheets.properties.title").Context(ctx).Do()
	if err != nil {
		return nil, fmt.Errorf("get spreadsheet: %w", err)
	}

	info := &SheetInfo{
		SpreadsheetID: spreadsheetID,
		Title:         sp.Properties.Title,
		Sheets:        make([]string, 0, len(sp.Sheets)),
	}
	for _, s := range sp.Sheets {
		info.Sheets = append(info.Sheets, s.Properties.Title)
	}
	return info, nil
}

// GetSheetPreview reads the first maxRows rows from a sheet, returning headers and data.
func GetSheetPreview(ctx context.Context, client *http.Client, spreadsheetID, sheetName string, maxRows int) (*SheetPreview, error) {
	srv, err := sheets.NewService(ctx, option.WithHTTPClient(client))
	if err != nil {
		return nil, fmt.Errorf("create sheets service: %w", err)
	}

	// Read enough rows for headers + preview
	rangeStr := fmt.Sprintf("'%s'!1:%d", sheetName, maxRows+1)
	resp, err := srv.Spreadsheets.Values.Get(spreadsheetID, rangeStr).Context(ctx).Do()
	if err != nil {
		return nil, fmt.Errorf("get values: %w", err)
	}

	preview := &SheetPreview{
		Headers: []string{},
		Rows:    [][]string{},
	}

	if len(resp.Values) == 0 {
		return preview, nil
	}

	// First row is headers
	for _, cell := range resp.Values[0] {
		preview.Headers = append(preview.Headers, fmt.Sprintf("%v", cell))
	}

	// Remaining rows are data
	for _, row := range resp.Values[1:] {
		strRow := make([]string, len(preview.Headers))
		for i, cell := range row {
			if i < len(strRow) {
				strRow[i] = fmt.Sprintf("%v", cell)
			}
		}
		preview.Rows = append(preview.Rows, strRow)
	}

	// Get total row count
	totalResp, err := srv.Spreadsheets.Values.Get(spreadsheetID, fmt.Sprintf("'%s'", sheetName)).Context(ctx).Do()
	if err == nil {
		preview.TotalRows = len(totalResp.Values) - 1 // exclude header
		if preview.TotalRows < 0 {
			preview.TotalRows = 0
		}
	}

	return preview, nil
}

// ReadAllRows reads all rows (excluding header) from a sheet.
// Returns the header row and all data rows.
func ReadAllRows(ctx context.Context, client *http.Client, spreadsheetID, sheetName string) (headers []string, rows [][]string, err error) {
	srv, err := sheets.NewService(ctx, option.WithHTTPClient(client))
	if err != nil {
		return nil, nil, fmt.Errorf("create sheets service: %w", err)
	}

	resp, err := srv.Spreadsheets.Values.Get(spreadsheetID, fmt.Sprintf("'%s'", sheetName)).Context(ctx).Do()
	if err != nil {
		return nil, nil, fmt.Errorf("get values: %w", err)
	}

	if len(resp.Values) == 0 {
		return nil, nil, nil
	}

	// First row = headers
	for _, cell := range resp.Values[0] {
		headers = append(headers, fmt.Sprintf("%v", cell))
	}

	// Remaining rows = data
	for _, row := range resp.Values[1:] {
		strRow := make([]string, len(headers))
		for i, cell := range row {
			if i < len(strRow) {
				strRow[i] = fmt.Sprintf("%v", cell)
			}
		}
		rows = append(rows, strRow)
	}

	return headers, rows, nil
}
