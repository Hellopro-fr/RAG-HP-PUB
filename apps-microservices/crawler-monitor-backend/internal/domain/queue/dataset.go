// Package queue provides filesystem-backed dataset listing and request-queue inspection.
//
// Dataset layout (mirrors fixture.js + server.js listDatasetDirs / countValidJsonFiles):
//
//	<jobID>/storage/datasets/
//	    <domain>/          ← success entries (plain JSON with "url" field)
//	    error-<domain>/    ← error entries  (JSON with "url", optional "errorMessages", "statusCode", "statusText")
//	    nfr-<domain>/      ← NFR entries    (plain JSON with "url" field)
//
// Request-queues layout (mirrors server.js findRequestQueuesDir):
//
//	<jobID>/storage/request_queues/<domain>/<N>.json  ← Crawlee v3 on-disk shape
package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

// ---- Dataset Counts ----

// DatasetCounts holds the number of valid JSON files in each category dir.
type DatasetCounts struct {
	Success int `json:"success"`
	Error   int `json:"error"`
	NFR     int `json:"nfr"`
}

// datasetDirs holds the resolved absolute paths for each category subdirectory.
// A path is empty string when the directory does not exist.
type datasetDirs struct {
	mainDir  string
	errorDir string
	nfrDir   string
}

// listDatasetDirs inspects <jobID>/storage/datasets/ and categorises its subdirs.
// Mirrors listDatasetDirs() in server.js.
func listDatasetDirs(ctx context.Context, fs *filestore.Storage, jobID string) datasetDirs {
	entries, err := fs.ListDir(ctx, jobID, "storage", "datasets")
	if err != nil {
		return datasetDirs{}
	}
	var mainName, errorName, nfrName string
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		name := e.Name()
		switch {
		case strings.HasPrefix(name, "error-") && errorName == "":
			errorName = name
		case strings.HasPrefix(name, "nfr-") && nfrName == "":
			nfrName = name
		case mainName == "":
			mainName = name
		}
	}
	base := filepath.Join(fs.Base(), jobID, "storage", "datasets")
	toPath := func(name string) string {
		if name == "" {
			return ""
		}
		return filepath.Join(base, name)
	}
	return datasetDirs{
		mainDir:  toPath(mainName),
		errorDir: toPath(errorName),
		nfrDir:   toPath(nfrName),
	}
}

// countValidJSONFiles counts .json files in dir that are parseable.
// Mirrors countValidJsonFiles() in server.js.
func countValidJSONFiles(dir string) int {
	if dir == "" {
		return 0
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return 0
	}
	count := 0
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		var tmp any
		if json.Unmarshal(raw, &tmp) == nil {
			count++
		}
	}
	return count
}

// CountDatasets returns the number of valid JSON entries in each dataset category.
func CountDatasets(ctx context.Context, storage *filestore.Storage, jobID string) DatasetCounts {
	dirs := listDatasetDirs(ctx, storage, jobID)
	return DatasetCounts{
		Success: countValidJSONFiles(dirs.mainDir),
		Error:   countValidJSONFiles(dirs.errorDir),
		NFR:     countValidJSONFiles(dirs.nfrDir),
	}
}

// ---- Dataset URL Listing ----

// DatasetEntry is a single item returned by ListDatasetURLs.
type DatasetEntry struct {
	URL   string  `json:"url"`
	Error *string `json:"error,omitempty"` // non-nil only for error category
}

// URLPage is the paginated response for /api/jobs/:id/dataset/urls.
type URLPage struct {
	Category   string         `json:"category"`
	Total      int            `json:"total"`
	Page       int            `json:"page"`
	TotalPages int            `json:"totalPages"`
	Items      []DatasetEntry `json:"items"`
}

// rawURLEntry is the on-disk JSON shape used by both success and error datasets.
type rawURLEntry struct {
	URL          string   `json:"url"`
	ErrorMessages []string `json:"errorMessages"`
	StatusCode   *int     `json:"statusCode"`
	StatusText   string   `json:"statusText"`
}

// deriveErrorMessage mirrors deriveErrorMessage() in server.js.
func deriveErrorMessage(e rawURLEntry) string {
	if len(e.ErrorMessages) > 0 {
		return e.ErrorMessages[0]
	}
	if e.StatusCode != nil {
		text := ""
		if e.StatusText != "" {
			text = " " + e.StatusText
		}
		return fmt.Sprintf("HTTP %d%s", *e.StatusCode, text)
	}
	return "Unknown error"
}

// ErrInvalidCategory is returned when the category parameter is not valid.
var ErrInvalidCategory = fmt.Errorf("Invalid category. Must be one of: success, error, nfr")

// ListDatasetURLs returns a paginated list of dataset URLs for a given category.
// page is 1-indexed; limit is capped at 200.
// Mirrors the /api/jobs/:id/dataset/urls handler in server.js.
func ListDatasetURLs(ctx context.Context, storage *filestore.Storage, jobID, category string, page, limit int, search string) (*URLPage, error) {
	if category != "success" && category != "error" && category != "nfr" {
		return nil, ErrInvalidCategory
	}
	// Clamp pagination params.
	if page < 1 {
		page = 1
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 200 {
		limit = 200
	}

	dirs := listDatasetDirs(ctx, storage, jobID)
	var dir string
	switch category {
	case "success":
		dir = dirs.mainDir
	case "error":
		dir = dirs.errorDir
	case "nfr":
		dir = dirs.nfrDir
	}

	if dir == "" {
		return &URLPage{Category: category, Total: 0, Page: page, TotalPages: 0, Items: []DatasetEntry{}}, nil
	}

	// Check dir exists.
	if _, err := os.Stat(dir); err != nil {
		return &URLPage{Category: category, Total: 0, Page: page, TotalPages: 0, Items: []DatasetEntry{}}, nil
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("readdir: %w", err)
	}

	searchLower := strings.ToLower(search)

	valid := make([]DatasetEntry, 0)
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		var data rawURLEntry
		if err := json.Unmarshal(raw, &data); err != nil {
			continue
		}
		if data.URL == "" {
			continue
		}
		if searchLower != "" && !strings.Contains(strings.ToLower(data.URL), searchLower) {
			continue
		}
		entry := DatasetEntry{URL: data.URL}
		if category == "error" {
			msg := deriveErrorMessage(data)
			entry.Error = &msg
		}
		valid = append(valid, entry)
	}

	total := len(valid)
	totalPages := 0
	if limit > 0 && total > 0 {
		totalPages = (total + limit - 1) / limit
	}
	start := (page - 1) * limit
	var items []DatasetEntry
	if start < total {
		end := start + limit
		if end > total {
			end = total
		}
		items = valid[start:end]
	} else {
		items = []DatasetEntry{}
	}
	return &URLPage{
		Category:   category,
		Total:      total,
		Page:       page,
		TotalPages: totalPages,
		Items:      items,
	}, nil
}

// ---- Request Queues ----

// QueueEntry is a single request-queue file item.
type QueueEntry struct {
	Name          string   `json:"name"`
	Domain        string   `json:"domain"`
	Path          string   `json:"path"`
	URL           string   `json:"url"`
	Method        string   `json:"method"`
	RetryCount    int      `json:"retryCount"`
	ErrorMessages []string `json:"errorMessages"`
	IsHandled     bool     `json:"isHandled"`
}

// QueueCounts holds unfiltered queue item counts.
type QueueCounts struct {
	Total   int `json:"total"`
	Pending int `json:"pending"`
	Handled int `json:"handled"`
}

// QueuePage is the paginated response for /api/jobs/:id/request-queues.
type QueuePage struct {
	Items      []QueueEntry `json:"items"`
	Total      int          `json:"total"`
	Page       int          `json:"page"`
	Limit      int          `json:"limit"`
	TotalPages int          `json:"totalPages"`
	Counts     QueueCounts  `json:"counts"`
}

// crawleeFile mirrors the Crawlee v3 on-disk JSON shape emitted by fixture.js.
type crawleeFile struct {
	ID            string   `json:"id"`
	URL           string   `json:"url"`
	Method        string   `json:"method"`
	OrderNo       *int64   `json:"orderNo"` // null = handled, positive int = pending
	RetryCount    int      `json:"retryCount"`
	UniqueKey     string   `json:"uniqueKey"`
	ErrorMessages []string `json:"errorMessages"`
}

// findRequestQueuesBase returns the base path for request queues or "".
// Mirrors findRequestQueuesDir() in server.js (two candidate paths).
func findRequestQueuesBase(storage *filestore.Storage, jobID string) string {
	candidates := [][]string{
		{jobID, "storage", "request_queues"},
		{jobID, "request_queues"},
	}
	for _, parts := range candidates {
		p := filepath.Join(append([]string{storage.Base()}, parts...)...)
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return ""
}

// ListRequestQueues lists and paginates request-queue files for a job.
// status: "all" | "pending" | "handled". search is case-insensitive substring on rawContent.
func ListRequestQueues(ctx context.Context, storage *filestore.Storage, jobID, search, status string, page, limit int) (*QueuePage, error) {
	if status != "pending" && status != "handled" {
		status = "all"
	}
	if page < 1 {
		page = 1
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 200 {
		limit = 200
	}

	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return &QueuePage{
			Items:  []QueueEntry{},
			Total:  0, Page: page, Limit: limit, TotalPages: 0,
			Counts: QueueCounts{},
		}, nil
	}

	domainDirs, err := os.ReadDir(baseDir)
	if err != nil {
		return nil, fmt.Errorf("readdir queues: %w", err)
	}

	type fileItem struct {
		QueueEntry
		rawContent string
	}
	allFiles := make([]fileItem, 0)

	for _, de := range domainDirs {
		if !de.IsDir() {
			continue
		}
		domainName := de.Name()
		domainPath := filepath.Join(baseDir, domainName)
		files, err := os.ReadDir(domainPath)
		if err != nil {
			continue
		}
		for _, f := range files {
			if f.IsDir() || !strings.HasSuffix(f.Name(), ".json") {
				continue
			}
			filePath := filepath.Join(domainPath, f.Name())
			rawBytes, err := os.ReadFile(filePath)
			rawStr := ""
			if err == nil {
				rawStr = string(rawBytes)
			}
			entry := QueueEntry{
				Name:   f.Name(),
				Domain: domainName,
				Path:   filepath.Join(domainName, f.Name()),
				URL:    "Error reading file",
				Method: "UNKNOWN",
			}
			if err == nil {
				var cf crawleeFile
				if json.Unmarshal(rawBytes, &cf) == nil {
					entry.URL = cf.URL
					entry.Method = cf.Method
					entry.RetryCount = cf.RetryCount
					entry.ErrorMessages = cf.ErrorMessages
					entry.IsHandled = cf.OrderNo == nil
				}
			}
			allFiles = append(allFiles, fileItem{QueueEntry: entry, rawContent: rawStr})
		}
	}

	// Unfiltered counts.
	counts := QueueCounts{Total: len(allFiles)}
	for _, f := range allFiles {
		if f.IsHandled {
			counts.Handled++
		} else {
			counts.Pending++
		}
	}

	// Apply search + status filter.
	searchLower := strings.ToLower(search)
	matching := make([]fileItem, 0, len(allFiles))
	for _, f := range allFiles {
		if searchLower != "" && !strings.Contains(strings.ToLower(f.rawContent), searchLower) {
			continue
		}
		if status == "pending" && f.IsHandled {
			continue
		}
		if status == "handled" && !f.IsHandled {
			continue
		}
		matching = append(matching, f)
	}

	total := len(matching)
	totalPages := 0
	if limit > 0 && total > 0 {
		totalPages = (total + limit - 1) / limit
	}
	start := (page - 1) * limit
	items := make([]QueueEntry, 0)
	if start < total {
		end := start + limit
		if end > total {
			end = total
		}
		for _, f := range matching[start:end] {
			items = append(items, f.QueueEntry)
		}
	}
	return &QueuePage{
		Items:      items,
		Total:      total,
		Page:       page,
		Limit:      limit,
		TotalPages: totalPages,
		Counts:     counts,
	}, nil
}

// ReadQueueFile reads and parses a single request-queue file.
// Returns ErrNotFound if the file does not exist, ErrPathEscape if path is unsafe.
func ReadQueueFile(ctx context.Context, storage *filestore.Storage, jobID, domain, filename string) ([]byte, error) {
	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return nil, fs.ErrNotExist
	}
	// Build and validate target path.
	target := filepath.Clean(filepath.Join(baseDir, domain, filename))
	if !strings.HasPrefix(target, baseDir+string(os.PathSeparator)) {
		return nil, filestore.ErrPathEscape
	}
	if _, err := os.Stat(target); err != nil {
		return nil, fs.ErrNotExist
	}
	raw, err := os.ReadFile(target)
	if err != nil {
		return nil, err
	}
	// Validate it is valid JSON.
	var tmp any
	if err := json.Unmarshal(raw, &tmp); err != nil {
		return nil, err
	}
	return raw, nil
}

// WriteQueueFile atomically writes JSON content to a request-queue file.
func WriteQueueFile(ctx context.Context, storage *filestore.Storage, jobID, domain, filename string, data []byte) error {
	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return fs.ErrNotExist
	}
	target := filepath.Clean(filepath.Join(baseDir, domain, filename))
	if !strings.HasPrefix(target, baseDir+string(os.PathSeparator)) {
		return filestore.ErrPathEscape
	}
	return os.WriteFile(target, data, 0o644)
}
