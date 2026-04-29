package httpapi

import (
	"errors"
	"io"
	"io/fs"
	"net/http"
	"strconv"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/queue"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/go-chi/chi/v5"
)

// queuesListHandler handles GET /api/jobs/{id}/request-queues.
// Query params: page, limit, search, status (all|pending|handled).
// Mirrors server.js:625.
func queuesListHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		page, _ := strconv.Atoi(r.URL.Query().Get("page"))
		limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
		if limit == 0 {
			limit = 50
		}
		search := r.URL.Query().Get("search")
		status := r.URL.Query().Get("status")

		result, err := queue.ListRequestQueues(r.Context(), fs, id, search, status, page, limit)
		if err != nil {
			WriteError(w, 500, "Failed to list request queues")
			return
		}
		WriteJSON(w, 200, result)
	}
}

// queuesReadFileHandler handles GET /api/jobs/{id}/request-queues/{domain}/{filename}.
// Returns the raw JSON content of a single queue file.
// Mirrors server.js:718.
func queuesReadFileHandler(storage *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		domain := chi.URLParam(r, "domain")
		filename := chi.URLParam(r, "filename")

		raw, err := queue.ReadQueueFile(r.Context(), storage, id, domain, filename)
		if err != nil {
			if errors.Is(err, filestore.ErrPathEscape) {
				WriteError(w, 400, "Invalid path")
				return
			}
			if errors.Is(err, fs.ErrNotExist) {
				WriteError(w, 404, "File not found")
				return
			}
			WriteError(w, 500, "Failed to read file")
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.WriteHeader(200)
		_, _ = w.Write(raw)
	}
}

// queuesWriteFileHandler handles POST /api/jobs/{id}/request-queues/{domain}/{filename}.
// Accepts up to 50MB body; writes JSON content to the queue file.
// Mirrors server.js:745.
func queuesWriteFileHandler(storage *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		domain := chi.URLParam(r, "domain")
		filename := chi.URLParam(r, "filename")

		r.Body = http.MaxBytesReader(w, r.Body, MaxBodyBytes)
		data, err := io.ReadAll(r.Body)
		if err != nil {
			if errors.Is(err, &http.MaxBytesError{}) || err.Error() == "http: request body too large" {
				WriteError(w, 413, "Request body too large")
				return
			}
			WriteError(w, 500, "Failed to read body")
			return
		}

		if err := queue.WriteQueueFile(r.Context(), storage, id, domain, filename, data); err != nil {
			if errors.Is(err, filestore.ErrPathEscape) {
				WriteError(w, 400, "Invalid path")
				return
			}
			if errors.Is(err, fs.ErrNotExist) {
				WriteError(w, 404, "Request queues directory not found")
				return
			}
			WriteError(w, 500, "Failed to save file")
			return
		}
		WriteJSON(w, 200, map[string]string{"status": "ok"})
	}
}
