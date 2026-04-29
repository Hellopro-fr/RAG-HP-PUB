// Package queue — replay.go
// Traduit le handler GET /api/jobs/:id/replay de server.js:320-454.
// Agrège : points de performance, métadonnées du job Redis, marqueurs d'événements,
// zones CPU chaudes, événements d'audit.
package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/jobperf"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/redis/go-redis/v9"
)

// ReplayJobInfo contient les métadonnées Redis du job (mirrors server.js:338-347).
type ReplayJobInfo struct {
	ID              string  `json:"id"`
	Domain          string  `json:"domain,omitempty"`
	Status          string  `json:"status,omitempty"`
	StartTime       string  `json:"start_time,omitempty"`
	CrawlMode       string  `json:"crawl_mode,omitempty"`
	OOMRestartCount int     `json:"oom_restart_count"`
	PreviousCrawlID *string `json:"previous_crawl_id,omitempty"`
}

// ReplayEvent est un marqueur d'événement sur la timeline (mirrors server.js:351-436).
type ReplayEvent struct {
	Ts       int64  `json:"ts"`
	Kind     string `json:"kind"`
	Label    string `json:"label"`
	Severity string `json:"severity"`
	// Champs optionnels selon le kind
	DurationMs *int64  `json:"duration_ms,omitempty"`
	Action     *string `json:"action,omitempty"`
	User       *string `json:"user,omitempty"`
}

// ReplayHotZone est un segment continu où cpu > highCPUThreshold (mirrors server.js:373-403).
type ReplayHotZone struct {
	From   int64   `json:"from"`
	To     int64   `json:"to"`
	MaxCPU float64 `json:"max_cpu"`
}

// ReplayResult est la réponse complète du endpoint /api/jobs/:id/replay (mirrors server.js:442-450).
type ReplayResult struct {
	JobID       string         `json:"job_id"`
	Job         *ReplayJobInfo `json:"job"`
	Points      []jobperf.Point  `json:"points"`
	Summary     *jobperf.Summary `json:"summary"`
	Events      []ReplayEvent  `json:"events"`
	HotZones    []ReplayHotZone `json:"hot_zones"`
	GeneratedAt string         `json:"generated_at"`
}

// ComputeReplay construit la réponse de replay pour un job.
// Retourne redis.Nil si le job n'existe pas dans Redis (→ 404 dans le handler).
// mirrors server.js:320-454.
func ComputeReplay(
	ctx context.Context,
	rdb *redis.Client,
	as *auditstore.Local,
	jobID string,
	highCPUThreshold float64,
) (*ReplayResult, error) {
	// 1. Lecture points + summary de performance
	perf := jobperf.Read(ctx, rdb, jobID)

	// 2. Lecture métadonnées du job dans Redis
	var jobInfo *ReplayJobInfo
	raw, err := rdb.Get(ctx, redisstore.JobPrefix+jobID).Result()
	if err == redis.Nil {
		// Job inconnu → 404
		return nil, redis.Nil
	}
	if err == nil && raw != "" {
		j := redisstore.RawJob{}
		if jsonErr := json.Unmarshal([]byte(raw), &j); jsonErr == nil {
			info := &ReplayJobInfo{
				OOMRestartCount: 0,
			}
			if v, ok := j["crawl_id"].(string); ok && v != "" {
				info.ID = v
			} else {
				info.ID = jobID
			}
			if v, ok := j["domain"].(string); ok {
				info.Domain = v
			}
			if v, ok := j["status"].(string); ok {
				info.Status = v
			}
			if v, ok := j["start_time"].(string); ok {
				info.StartTime = v
			}
			if v, ok := j["crawl_mode"].(string); ok {
				info.CrawlMode = v
			}
			if v, ok := j["oom_restart_count"].(float64); ok {
				info.OOMRestartCount = int(v)
			}
			if v, ok := j["previous_crawl_id"].(string); ok && v != "" {
				info.PreviousCrawlID = &v
			}
			jobInfo = info
		}
	}

	events := make([]ReplayEvent, 0)

	// 3. Marqueurs depuis le summary (mirrors server.js:353-370)
	if perf.Summary != nil {
		s := perf.Summary
		if s.PeakCPUAt != nil {
			sev := "info"
			if s.PeakCPU > highCPUThreshold {
				sev = "warn"
			}
			events = append(events, ReplayEvent{
				Ts:       *s.PeakCPUAt,
				Kind:     "peak_cpu",
				Label:    fmt.Sprintf("Peak CPU %.1f%%", s.PeakCPU*100),
				Severity: sev,
			})
		}
		if s.PeakRAMAt != nil {
			events = append(events, ReplayEvent{
				Ts:       *s.PeakRAMAt,
				Kind:     "peak_ram",
				Label:    fmt.Sprintf("Peak RAM %.0f MB", s.PeakRAM/1024/1024),
				Severity: "info",
			})
		}
	}

	// 4. Zones CPU chaudes : segments contigus où cpu > threshold (mirrors server.js:372-403)
	hotZones := make([]ReplayHotZone, 0)
	if len(perf.Points) > 1 {
		var zoneStart int64 = -1
		var zoneMaxCPU float64
		for _, p := range perf.Points {
			cpu := p.CPU
			if cpu > highCPUThreshold {
				if zoneStart == -1 {
					zoneStart = p.Ts
				}
				if cpu > zoneMaxCPU {
					zoneMaxCPU = cpu
				}
			} else if zoneStart != -1 {
				hotZones = append(hotZones, ReplayHotZone{From: zoneStart, To: p.Ts, MaxCPU: zoneMaxCPU})
				zoneStart = -1
				zoneMaxCPU = 0
			}
		}
		// Ferme la dernière zone ouverte à la fin de la série
		if zoneStart != -1 {
			last := perf.Points[len(perf.Points)-1]
			hotZones = append(hotZones, ReplayHotZone{From: zoneStart, To: last.Ts, MaxCPU: zoneMaxCPU})
		}
		// Construit les événements hot_cpu_zone (mirrors server.js:395-403)
		for _, z := range hotZones {
			durMs := z.To - z.From
			durSec := int64(math.Max(1, math.Round(float64(durMs)/1000)))
			label := fmt.Sprintf("CPU > %.0f%% pendant %ds (max %.0f%%)",
				highCPUThreshold*100, durSec, z.MaxCPU*100)
			dms := durMs
			events = append(events, ReplayEvent{
				Ts:         z.From,
				Kind:       "hot_cpu_zone",
				Label:      label,
				Severity:   "warn",
				DurationMs: &dms,
			})
		}
	}

	// 5. Événements OOM (mirrors server.js:406-414)
	if jobInfo != nil && jobInfo.OOMRestartCount > 0 && len(perf.Points) > 0 {
		suffix := ""
		if jobInfo.OOMRestartCount > 1 {
			suffix = "s"
		}
		events = append(events, ReplayEvent{
			Ts:       perf.Points[0].Ts,
			Kind:     "oom_summary",
			Label:    fmt.Sprintf("%d OOM restart%s pendant le crawl", jobInfo.OOMRestartCount, suffix),
			Severity: "critical",
		})
	}

	// 6. Entrées d'audit ciblant ce job (mirrors server.js:416-437, best-effort)
	if as != nil {
		var fromTime time.Time
		windowMs := int64(7 * 24 * 60 * 60 * 1000)
		if len(perf.Points) > 0 {
			fromTime = time.UnixMilli(perf.Points[0].Ts - 60_000).UTC()
		} else {
			fromTime = time.Now().Add(-time.Duration(windowMs) * time.Millisecond).UTC()
		}
		toTime := time.Now().UTC()

		page, auditErr := as.Read(ctx, auditstore.Filter{
			From:   fromTime,
			To:     toTime,
			Target: jobID,
			Limit:  200,
		})
		if auditErr == nil && page != nil {
			for _, e := range page.Items {
				tsStr, _ := e["ts"].(string)
				t, parseErr := time.Parse(time.RFC3339Nano, tsStr)
				if parseErr != nil {
					continue
				}
				action, _ := e["action"].(string)
				user, _ := e["user"].(string)
				status, _ := e["status"].(string)

				sev := "info"
				if status == "error" {
					sev = "warn"
				}
				suffix := ""
				if status == "error" {
					suffix = " (échec)"
				}
				a := action
				u := user
				events = append(events, ReplayEvent{
					Ts:       t.UnixMilli(),
					Kind:     "audit",
					Label:    fmt.Sprintf("%s par %s%s", action, user, suffix),
					Severity: sev,
					Action:   &a,
					User:     &u,
				})
			}
		}
	}

	// Tri chronologique des événements (mirrors server.js:439-440)
	sortEvents(events)

	// Points vides → slice non-nil pour JSON []
	pts := perf.Points
	if pts == nil {
		pts = []jobperf.Point{}
	}

	return &ReplayResult{
		JobID:       jobID,
		Job:         jobInfo,
		Points:      pts,
		Summary:     perf.Summary,
		Events:      events,
		HotZones:    hotZones,
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
	}, nil
}

// sortEvents trie les événements par ts croissant (mirrors server.js:439-440).
func sortEvents(events []ReplayEvent) {
	sort.SliceStable(events, func(i, j int) bool {
		return events[i].Ts < events[j].Ts
	})
}
