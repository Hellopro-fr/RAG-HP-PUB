package httpapi

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/callbacks"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

// callbacksListHandler handles GET /api/callbacks.
// Retourne la liste des callbacks échoués stockés dans Redis.
// Traduit server.js:1538-1551.
func callbacksListHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		raw, err := rs.Raw().LRange(ctx, redisstore.FailedCallbacksKey, 0, -1).Result()
		if err != nil {
			WriteError(w, 500, "Failed to fetch callbacks")
			return
		}
		items := make([]any, 0, len(raw))
		for _, s := range raw {
			var parsed any
			if json.Unmarshal([]byte(s), &parsed) == nil {
				items = append(items, parsed)
			} else {
				items = append(items, map[string]string{"raw": s})
			}
		}
		WriteJSON(w, 200, map[string]any{
			"count": len(items),
			"items": items,
		})
	}
}

// callbacksRetryHandler handles POST /api/callbacks/{idx}/retry.
// Rejoue le callback à l'index donné. En cas de succès, le retire de la liste Redis.
// En cas d'échec, incrémente manual_retry_attempts et met à jour l'entrée.
// Traduit server.js:1553-1604.
func callbacksRetryHandler(rs *redisstore.Client, audit AuditAppender) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		idxStr := chi.URLParam(r, "idx")
		idx, err := strconv.Atoi(idxStr)
		if err != nil || idx < 0 {
			WriteError(w, 400, "Invalid index")
			return
		}

		original, err := rs.Raw().LIndex(ctx, redisstore.FailedCallbacksKey, int64(idx)).Result()
		if err == redis.Nil {
			WriteError(w, 404, "Entry not found")
			return
		}
		if err != nil {
			WriteError(w, 500, "Failed to fetch callback")
			return
		}

		var entry callbacks.Callback
		if err := json.Unmarshal([]byte(original), &entry); err != nil {
			WriteError(w, 400, "Stored entry is not valid JSON")
			return
		}

		result := callbacks.Replay(ctx, entry)

		if audit != nil {
			_ = audit.Append(ctx, map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"action": "replay_callback",
				"target": idxStr,
				"status": map[bool]string{true: "ok", false: "error"}[result.OK],
			})
		}

		if result.OK {
			// Retire la première occurrence correspondant à l'entrée originale
			removed, _ := rs.Raw().LRem(ctx, redisstore.FailedCallbacksKey, 1, original).Result()
			WriteJSON(w, 200, map[string]any{
				"success":               true,
				"status":                result.Status,
				"error":                 nil,
				"removed":               removed > 0,
				"manual_retry_attempts": entry.ManualRetryAttempts + 1,
			})
		} else {
			// Met à jour l'entrée avec le compteur de retry et l'erreur
			entry.ManualRetryAttempts++
			updated, _ := json.Marshal(entry)
			rs.Raw().LSet(ctx, redisstore.FailedCallbacksKey, int64(idx), string(updated))
			WriteJSON(w, 502, map[string]any{
				"success":               false,
				"status":                result.Status,
				"error":                 result.Error,
				"manual_retry_attempts": entry.ManualRetryAttempts,
			})
		}
	}
}

// callbacksDeleteHandler handles DELETE /api/callbacks/{idx}.
// Supprime l'entrée à l'index donné de la liste Redis.
// Traduit server.js:1606-1625.
func callbacksDeleteHandler(rs *redisstore.Client, audit AuditAppender) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		idxStr := chi.URLParam(r, "idx")
		idx, err := strconv.Atoi(idxStr)
		if err != nil || idx < 0 {
			WriteError(w, 400, "Invalid index")
			return
		}

		original, err := rs.Raw().LIndex(ctx, redisstore.FailedCallbacksKey, int64(idx)).Result()
		if err == redis.Nil {
			WriteError(w, 404, "Entry not found")
			return
		}
		if err != nil {
			WriteError(w, 500, "Failed to fetch callback")
			return
		}

		removed, _ := rs.Raw().LRem(ctx, redisstore.FailedCallbacksKey, 1, original).Result()

		if audit != nil {
			_ = audit.Append(ctx, map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"action": "delete_callback",
				"target": idxStr,
				"status": "ok",
			})
		}

		WriteJSON(w, 200, map[string]any{"deleted": removed > 0})
	}
}

// callbacksClearHandler handles POST /api/callbacks/clear.
// Supprime l'intégralité de la liste des callbacks échoués.
// Retourne {"cleared": N}. Traduit server.js:1627-1641.
func callbacksClearHandler(rs *redisstore.Client, audit AuditAppender) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		cleared, err := rs.Raw().LLen(ctx, redisstore.FailedCallbacksKey).Result()
		if err != nil {
			WriteError(w, 500, "Failed to clear callbacks")
			return
		}
		rs.Raw().Del(ctx, redisstore.FailedCallbacksKey)

		if audit != nil {
			_ = audit.Append(ctx, map[string]any{
				"ts":      time.Now().UTC().Format(time.RFC3339Nano),
				"action":  "clear_callbacks",
				"cleared": cleared,
				"status":  "ok",
			})
		}

		WriteJSON(w, 200, map[string]any{"cleared": cleared})
	}
}
