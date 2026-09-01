package httpapi

import (
	"context"
	"errors"
	"io/fs"
	"log/slog"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/joblog"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

// dateFields : champs de date d'un job normalises en RFC3339 UTC avant reponse.
// crawler-service ecrit des dates naives ("2026-08-28 13:20:03.306901") que le
// frontend interprete en heure locale.
var dateFields = []string{
	"start_time", "end_time", "finished_at", "archived_at",
	"stashed_at", "downloaded_at", "last_heartbeat",
}

// secretParamRe : filet de securite sur l'allowlist de configuration. Aucune
// cle de configAllowlist ne doit matcher ; si ca arrive un jour, la valeur est
// tue et l'incident est logue plutot que publie au dashboard.
var secretParamRe = regexp.MustCompile(`(?i)proxy|apify|token|secret|password|key|auth`)

// redactedFields : champs jamais exposes par l'API (secrets d'appel, chemins
// serveur, PID, cle Redis interne).
var redactedFields = []string{
	"params", "callback_url", "failure_callback_url",
	"storage_path", "start_url", "pid", "_redisKey",
}

// configAllowlist : parametres de crawl exposables, avec leur nom de sortie.
var configAllowlist = map[string]string{
	"crawlMode":       "strategy",
	"maxCrawlDepth":   "depth",
	"maxConcurrency":  "concurrency",
	"perminute":       "perminute",
	"method":          "method",
	"typecrawling":    "typecrawling",
	"cms":             "cms",
	"camoufox":        "camoufox",
	"queuelimit":      "queuelimit",
	"maxErrorRate":    "maxErrorRate",
	"previousCrawlId": "previousCrawlId",
}

// jobsWindowMap : fenetres acceptees par le filtre ?window= de la liste.
var jobsWindowMap = map[string]int64{
	"15m": 15 * 60 * 1000,
	"1h":  60 * 60 * 1000,
	"6h":  6 * 60 * 60 * 1000,
	"24h": 24 * 60 * 60 * 1000,
	"7d":  7 * 24 * 60 * 60 * 1000,
	"30d": 30 * 24 * 60 * 60 * 1000,
}

// redactJob retourne une copie du job sans les champs sensibles.
func redactJob(j redisstore.RawJob) redisstore.RawJob {
	out := make(redisstore.RawJob, len(j))
	for k, v := range j {
		out[k] = v
	}
	for _, k := range redactedFields {
		delete(out, k)
	}
	return out
}

// normalizeDates convertit sur place les champs de date en RFC3339 UTC.
func normalizeDates(j redisstore.RawJob) {
	for _, k := range dateFields {
		v, ok := j[k]
		if !ok || v == nil {
			continue
		}
		if iso := datetime.AnyToISO(v); iso != "" {
			j[k] = iso
		}
	}
}

// jobConfig extrait de params la vue non sensible de la configuration de crawl.
func jobConfig(j redisstore.RawJob) map[string]any {
	cfg := map[string]any{}
	params, _ := j["params"].(map[string]any)
	for k, v := range params {
		name, ok := configAllowlist[k]
		if !ok {
			continue
		}
		if secretParamRe.MatchString(k) {
			slog.Error("config.allowlist_leak", "param", k)
			continue
		}
		cfg[name] = v
	}
	return cfg
}

// stripQuery retire la query string (et le fragment) d'une URL de callback :
// les tokens d'authentification y sont frequemment passes.
func stripQuery(raw string) string {
	if raw == "" {
		return ""
	}
	if u, err := url.Parse(raw); err == nil {
		u.RawQuery = ""
		u.Fragment = ""
		return u.String()
	}
	if i := strings.IndexAny(raw, "?#"); i >= 0 {
		return raw[:i]
	}
	return raw
}

// jobCallback resume l'etat des webhooks du job sans exposer les URLs completes.
func jobCallback(j redisstore.RawJob) map[string]any {
	cbURL, _ := j["callback_url"].(string)
	failureURL, _ := j["failure_callback_url"].(string)
	status := "pending"
	if v, ok := j["failure_webhook_request_id"]; ok && v != nil && v != "" {
		status = "failed"
	} else if v, ok := j["terminal_webhook_request_id"]; ok && v != nil && v != "" {
		status = "sent"
	} else if cbURL == "" && failureURL == "" {
		// Aucun webhook configure : "pending" laissait croire a un envoi
		// en attente qui n'arrivera jamais.
		status = "none"
	}
	return map[string]any{
		"url":         stripQuery(cbURL),
		"failure_url": stripQuery(failureURL),
		"status":      status,
	}
}

// jobsListHandler handles GET /api/jobs?status=&window=
// Reponse : tableau de jobs (forme inchangee), tries par start_time decroissant.
func jobsListHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		statusFilter := r.URL.Query().Get("status")
		var minStart int64 = -1
		if windowStr := r.URL.Query().Get("window"); windowStr != "" {
			windowMs, ok := jobsWindowMap[windowStr]
			if !ok {
				WriteError(w, 400, "Invalid window. Use '15m', '1h', '6h', '24h', '7d' or '30d'.")
				return
			}
			minStart = time.Now().UnixMilli() - windowMs
		}

		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}

		out := make([]redisstore.RawJob, 0, len(jobs))
		for _, j := range jobs {
			if statusFilter != "" {
				if s, _ := j["status"].(string); s != statusFilter {
					continue
				}
			}
			if minStart > 0 {
				// Une date illisible (-1) n'est pas une date ancienne : le
				// job reste visible plutot que de disparaitre du dashboard
				// des qu'un ?window= est demande.
				if ms := datetime.ParseAnyMs(j["start_time"]); ms > 0 && ms < minStart {
					continue
				}
			}
			red := redactJob(j)
			normalizeDates(red)
			out = append(out, red)
		}

		// Tri numerique : comparer les chaines ISO echoue des que les formats
		// different (naive vs offset).
		sort.SliceStable(out, func(i, j int) bool {
			return datetime.ParseAnyMs(out[i]["start_time"]) > datetime.ParseAnyMs(out[j]["start_time"])
		})
		WriteJSON(w, 200, out)
	}
}

// jobsDetailsHandler returns the job document merged with crawler.log parse
// results (stats / errors / warnings / rawContent / hasStats) when the log
// file exists. Mirrors server.js:462-501.
func jobsDetailsHandler(rs *redisstore.Client, fileStore *filestore.Storage) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		job, err := rs.GetJob(r.Context(), id)
		if errors.Is(err, redis.Nil) {
			WriteError(w, 404, "Job not found")
			return
		}
		if err != nil {
			WriteError(w, 500, "Failed to read job")
			return
		}
		// config et callback sont derives AVANT la redaction (ils lisent params
		// et les *_callback_url), puis les champs bruts sont retires.
		cfg := jobConfig(job)
		cb := jobCallback(job)
		safeJob := redactJob(job)
		normalizeDates(safeJob)
		safeJob["config"] = cfg
		safeJob["callback"] = cb
		mergeJobLog(r.Context(), fileStore, id, safeJob)
		WriteJSON(w, 200, safeJob)
	}
}

// mergeJobLog reads <id>/crawler.log via the FileStore and, if found, merges
// the parsed payload into job. Missing log file is non-fatal — defaults are
// injected so the frontend always finds the expected fields.
func mergeJobLog(ctx context.Context, fileStore *filestore.Storage, id string, job redisstore.RawJob) {
	defaults := func() {
		if _, ok := job["stats"]; !ok {
			job["stats"] = nil
		}
		if _, ok := job["errors"]; !ok {
			job["errors"] = []string{}
		}
		if _, ok := job["warnings"]; !ok {
			job["warnings"] = []string{}
		}
		if _, ok := job["rawContent"]; !ok {
			job["rawContent"] = ""
		}
		if _, ok := job["hasStats"]; !ok {
			job["hasStats"] = false
		}
	}
	if fileStore == nil {
		defaults()
		return
	}
	raw, err := fileStore.Read(ctx, id, "crawler.log")
	if err != nil {
		if !errors.Is(err, fs.ErrNotExist) {
			defaults()
			return
		}
		defaults()
		return
	}
	parsed := joblog.Parse(string(raw))
	job["stats"] = parsed.Stats
	job["errors"] = parsed.Errors
	job["warnings"] = parsed.Warnings
	job["rawContent"] = parsed.RawContent
	job["hasStats"] = parsed.HasStats
}
