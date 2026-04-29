package httpapi

import (
	"net/http"
	"strconv"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/queue"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/go-chi/chi/v5"
)

// datasetCountsHandler handles GET /api/jobs/{id}/dataset/counts.
// Returns {success, error, nfr} counts of valid JSON files in each dataset category dir.
// Mirrors server.js:1064.
func datasetCountsHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		counts := queue.CountDatasets(r.Context(), fs, id)
		WriteJSON(w, 200, counts)
	}
}

// datasetURLsHandler handles GET /api/jobs/{id}/dataset/urls.
// Query params: category (required), page, limit, search.
// Mirrors server.js:1092.
func datasetURLsHandler(fs *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		category := r.URL.Query().Get("category")
		page, _ := strconv.Atoi(r.URL.Query().Get("page"))
		limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
		if limit == 0 {
			limit = 50
		}
		search := r.URL.Query().Get("search")

		result, err := queue.ListDatasetURLs(r.Context(), fs, id, category, page, limit, search)
		if err != nil {
			if err == queue.ErrInvalidCategory {
				WriteError(w, 400, err.Error())
				return
			}
			WriteError(w, 500, "Failed to list dataset URLs")
			return
		}
		WriteJSON(w, 200, result)
	}
}

// datasetAnalyzeHandler handles GET /api/jobs/{id}/dataset/analyze.
// Retourne le nombre total, unique et en doublon, ainsi que la liste des groupes de doublons.
// Traduit server.js:1139-1212.
func datasetAnalyzeHandler(storage *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		result, err := queue.AnalyzeDuplicates(r.Context(), storage, id)
		if err != nil {
			WriteError(w, 500, "Failed to analyze dataset")
			return
		}
		WriteJSON(w, 200, result)
	}
}

// datasetDeduplicateHandler handles POST /api/jobs/{id}/dataset/deduplicate.
// Supprime les doublons dans le dataset principal du job, en gardant le fichier le plus récent.
// Retourne {"deleted": N}. Traduit server.js:1214-1297.
func datasetDeduplicateHandler(storage *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		deleted, err := queue.DeduplicateDataset(r.Context(), storage, id)
		if err != nil {
			WriteError(w, 500, "Failed to deduplicate dataset")
			return
		}
		WriteJSON(w, 200, map[string]int{"deleted": deleted})
	}
}
