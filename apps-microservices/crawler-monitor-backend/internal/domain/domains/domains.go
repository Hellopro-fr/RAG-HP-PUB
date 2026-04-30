// Package domains provides domain-level aggregation helpers.
//
// Each crawler job carries a `domain` field; we aggregate jobs by domain to
// power the /domains list and the per-domain detail page (run chain).
//
// Window default: 7 days. Reuses the same loadJobs pattern as systemStats.
package domains

import (
	"errors"
	"sort"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
)

var windowMap = map[string]int64{
	"24h": 24 * 60 * 60 * 1000,
	"7d":  7 * 24 * 60 * 60 * 1000,
	"30d": 30 * 24 * 60 * 60 * 1000,
}

// ParseDomainWindow parses "24h", "7d" or "30d" and returns duration in ms.
func ParseDomainWindow(input string) (int64, error) {
	ms, ok := windowMap[input]
	if !ok {
		return 0, errors.New("Invalid window. Use '24h', '7d' or '30d'.")
	}
	return ms, nil
}

var terminalOK = map[string]bool{"finished": true, "archived": true}
var terminalKO = map[string]bool{"failed": true}

// DomainSummary is an aggregated view of a domain's crawl activity.
type DomainSummary struct {
	Domain      string   `json:"domain"`
	TotalJobs   int      `json:"total_jobs"`
	Success     int      `json:"success"`
	Failure     int      `json:"failure"`
	Running     int      `json:"running"`
	Other       int      `json:"other"`
	SuccessRate *float64 `json:"success_rate"` // 0..1 or null
	OOMTotal    int      `json:"oom_total"`
	UpdateShare float64  `json:"update_share"`
	LastRunAt   *string  `json:"last_run_at"` // ISO string or null
	LastStatus  *string  `json:"last_status"`
}

// RawJob is the minimal job view consumed by domain aggregation.
type RawJob struct {
	ID              string `json:"id"`
	Domain          string `json:"domain"`
	StartTime       string `json:"start_time"`
	Status          string `json:"status"`
	CrawlMode       string `json:"crawl_mode"`
	OOMRestartCount int    `json:"oom_restart_count"`
	PreviousCrawlID string `json:"previous_crawl_id"`
}

// aggState tracks mutable state during domain aggregation (not exported).
type aggState struct {
	domain      string
	totalJobs   int
	success     int
	failure     int
	running     int
	other       int
	oomTotal    int
	updateCount int
	lastRunTs   int64
	lastRunAt   *string
	lastStatus  *string
}

// AggregateDomains groups jobs by domain and computes per-domain metrics.
// Returns an array sorted by last_run_at desc.
func AggregateDomains(jobs []RawJob, nowMs, windowMs int64) []DomainSummary {
	cutoff := nowMs - windowMs
	byDomain := make(map[string]*aggState)

	for i := range jobs {
		j := &jobs[i]
		if j.Domain == "" {
			continue
		}
		tMs := datetime.ParseStringMs(j.StartTime)
		if tMs < 0 {
			continue
		}
		if tMs < cutoff {
			continue
		}
		agg, exists := byDomain[j.Domain]
		if !exists {
			agg = &aggState{domain: j.Domain}
			byDomain[j.Domain] = agg
		}
		agg.totalJobs++
		status := j.Status
		if terminalOK[status] {
			agg.success++
		} else if terminalKO[status] {
			agg.failure++
		} else if status == "running" || status == "stopping" || status == "restarting_oom" {
			agg.running++
		} else {
			agg.other++
		}
		agg.oomTotal += j.OOMRestartCount
		if j.CrawlMode == "update" {
			agg.updateCount++
		}
		if tMs > agg.lastRunTs {
			agg.lastRunTs = tMs
			s := j.StartTime
			agg.lastRunAt = &s
			st := j.Status
			agg.lastStatus = &st
		}
	}

	out := make([]DomainSummary, 0, len(byDomain))
	for _, agg := range byDomain {
		completed := agg.success + agg.failure
		var successRate *float64
		if completed > 0 {
			sr := float64(agg.success) / float64(completed)
			successRate = &sr
		}
		updateShare := 0.0
		if agg.totalJobs > 0 {
			updateShare = float64(agg.updateCount) / float64(agg.totalJobs)
		}
		out = append(out, DomainSummary{
			Domain:      agg.domain,
			TotalJobs:   agg.totalJobs,
			Success:     agg.success,
			Failure:     agg.failure,
			Running:     agg.running,
			Other:       agg.other,
			SuccessRate: successRate,
			OOMTotal:    agg.oomTotal,
			UpdateShare: updateShare,
			LastRunAt:   agg.lastRunAt,
			LastStatus:  agg.lastStatus,
		})
	}
	// Sort by latest activity desc, matching JS: Date.parse(b.last_run_at||0) - Date.parse(a.last_run_at||0)
	sort.SliceStable(out, func(i, j int) bool {
		var ti, tj int64
		if out[i].LastRunAt != nil {
			ti = datetime.ParseStringMs(*out[i].LastRunAt)
		}
		if out[j].LastRunAt != nil {
			tj = datetime.ParseStringMs(*out[j].LastRunAt)
		}
		return ti > tj // desc
	})
	return out
}

// ChainEntry is a single entry in the run chain for a domain.
type ChainEntry struct {
	ID              string  `json:"id"`
	Status          string  `json:"status"`
	StartTime       string  `json:"start_time"`
	CrawlMode       *string `json:"crawl_mode"`
	OOMRestartCount int     `json:"oom_restart_count"`
}

// DomainDetail is the output of JobsForDomain.
type DomainDetail struct {
	Jobs  []RawJob     `json:"jobs"`
	Chain []ChainEntry `json:"chain"`
}

// JobsForDomain filters jobs for a single domain, sorted by start_time desc, with a
// "run chain" (linked via previous_crawl_id) starting from the most recent job.
func JobsForDomain(jobs []RawJob, domain string, windowMs, nowMs int64) DomainDetail {
	if nowMs == 0 {
		nowMs = time.Now().UnixMilli()
	}
	cutoff := nowMs - windowMs

	var filtered []RawJob
	for _, j := range jobs {
		if j.Domain != domain {
			continue
		}
		tMs := datetime.ParseStringMs(j.StartTime)
		if tMs < 0 || tMs < cutoff {
			continue
		}
		filtered = append(filtered, j)
	}
	// Sort newest first.
	sort.SliceStable(filtered, func(i, j int) bool {
		return datetime.ParseStringMs(filtered[i].StartTime) > datetime.ParseStringMs(filtered[j].StartTime)
	})

	// Build chain via previous_crawl_id starting from the most recent job.
	byID := make(map[string]*RawJob, len(filtered))
	for i := range filtered {
		byID[filtered[i].ID] = &filtered[i]
	}
	var chain []ChainEntry
	if len(filtered) > 0 {
		cur := &filtered[0]
		seen := make(map[string]bool)
		for cur != nil && !seen[cur.ID] {
			seen[cur.ID] = true
			var cm *string
			if cur.CrawlMode != "" {
				s := cur.CrawlMode
				cm = &s
			}
			chain = append(chain, ChainEntry{
				ID:              cur.ID,
				Status:          cur.Status,
				StartTime:       cur.StartTime,
				CrawlMode:       cm,
				OOMRestartCount: cur.OOMRestartCount,
			})
			if cur.PreviousCrawlID != "" {
				cur = byID[cur.PreviousCrawlID]
			} else {
				cur = nil
			}
		}
	}

	return DomainDetail{Jobs: filtered, Chain: chain}
}
