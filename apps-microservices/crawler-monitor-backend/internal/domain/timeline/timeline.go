// Package timeline provides bucket-based job timeline aggregation.
//
// Mirrors src/lib/timeline.js exactly:
//   - parseTimelineWindow validates the window key and returns (windowMs, granularityMs).
//   - AggregateTimeline buckets jobs by start_time into a fixed-width time series.
//   - AutoGranularity derives a sensible granularity for any window size.
//   - ComputeTimeline is the top-level function used by the HTTP handler.
package timeline

import (
	"errors"
	"math"
	"strings"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
)

// windowDef holds the presets for each named window.
type windowDef struct {
	Ms          int64
	GranularityMs int64
}

var windows = map[string]windowDef{
	"1h":  {Ms: 60 * 60 * 1000, GranularityMs: 60 * 1000},         // 60 buckets of 1 min
	"6h":  {Ms: 6 * 60 * 60 * 1000, GranularityMs: 5 * 60 * 1000}, // 72 buckets of 5 min
	"24h": {Ms: 24 * 60 * 60 * 1000, GranularityMs: 15 * 60 * 1000}, // 96 buckets of 15 min
	"7d":  {Ms: 7 * 24 * 60 * 60 * 1000, GranularityMs: 60 * 60 * 1000}, // 168 buckets of 1 hour
}

// ParseTimelineWindow validates a window key and returns (windowMs, granularityMs).
// Mirrors JS parseTimelineWindow.
func ParseTimelineWindow(input string) (windowMs, granularityMs int64, err error) {
	w, ok := windows[input]
	if !ok {
		return 0, 0, errors.New("Invalid window. Use '1h', '6h', '24h' or '7d'.")
	}
	return w.Ms, w.GranularityMs, nil
}

// Bucket is a single time slice in the timeline output.
type Bucket struct {
	Ts        int64 `json:"ts"`
	Success   int   `json:"success"`
	Failure   int   `json:"failure"`
	Running   int   `json:"running"`
	Other     int   `json:"other"`
	OomEvents int   `json:"oom_events"`
}

// Job is the minimal view needed for timeline aggregation.
type Job struct {
	StartTime       string
	Status          string
	OomRestartCount int
}

var terminalOK = map[string]bool{"finished": true, "archived": true}
var terminalKO = map[string]bool{"failed": true}
var runningSet = map[string]bool{"running": true, "stopping": true, "restarting_oom": true}

// AggregateTimeline buckets jobs by start_time into a fixed-width series.
// nowMs is used as the anchor for the window (testable).
// Mirrors JS aggregateTimeline exactly.
func AggregateTimeline(jobs []Job, nowMs, windowMs, granularityMs int64) []Bucket {
	// Snap "now" to a bucket boundary.
	lastBucketTs := (nowMs / granularityMs) * granularityMs
	firstBucketTs := lastBucketTs - windowMs + granularityMs
	numBuckets := int(math.Round(float64(windowMs) / float64(granularityMs)))

	buckets := make([]Bucket, numBuckets)
	for i := 0; i < numBuckets; i++ {
		buckets[i] = Bucket{Ts: firstBucketTs + int64(i)*granularityMs}
	}

	for _, j := range jobs {
		t := parseTimeMs(j.StartTime)
		if t < 0 {
			continue
		}
		if t < firstBucketTs || t >= firstBucketTs+int64(numBuckets)*granularityMs {
			continue
		}
		idx := int((t - firstBucketTs) / granularityMs)
		if idx < 0 || idx >= numBuckets {
			continue
		}
		status := strings.ToLower(j.Status)
		if terminalOK[status] {
			buckets[idx].Success++
		} else if terminalKO[status] {
			buckets[idx].Failure++
		} else if runningSet[status] {
			buckets[idx].Running++
		} else {
			buckets[idx].Other++
		}
		buckets[idx].OomEvents += j.OomRestartCount
	}

	return buckets
}

// AutoGranularity derives a sensible granularity keeping ~60-180 buckets.
// Mirrors JS autoGranularity.
func AutoGranularity(windowMs int64) int64 {
	const (
		h1  = int64(60 * 60 * 1000)
		h6  = int64(6 * 60 * 60 * 1000)
		h24 = int64(24 * 60 * 60 * 1000)
		d7  = int64(7 * 24 * 60 * 60 * 1000)
	)
	switch {
	case windowMs <= h1:
		return 60 * 1000
	case windowMs <= h6:
		return 5 * 60 * 1000
	case windowMs <= h24:
		return 15 * 60 * 1000
	case windowMs <= d7:
		return 60 * 60 * 1000
	default:
		return 6 * 60 * 60 * 1000
	}
}

// Result is the full timeline response payload.
type Result struct {
	Window        string   `json:"window"`
	WindowMs      int64    `json:"window_ms"`
	GranularityMs int64    `json:"granularity_ms"`
	From          *string  `json:"from"`
	To            *string  `json:"to"`
	Buckets       []Bucket `json:"buckets"`
	GeneratedAt   string   `json:"generated_at"`
}

// ComputeOptions holds optional parameters for ComputeTimeline.
type ComputeOptions struct {
	From string // ISO date string; if set together with To, use custom range
	To   string
}

// ComputeTimeline is the top-level aggregator used by the HTTP handler.
// jobs is the raw job slice already loaded from Redis.
// Mirrors JS computeTimeline.
func ComputeTimeline(jobs []Job, windowKey string, opts ComputeOptions) (*Result, error) {
	var windowMs, granularityMs, nowMs int64
	var windowLabel string
	var fromPtr, toPtr *string

	if opts.From != "" && opts.To != "" {
		fromMs := parseTimeMs(opts.From)
		toMs := parseTimeMs(opts.To)
		if fromMs < 0 || toMs < 0 || toMs <= fromMs {
			return nil, errors.New("Invalid 'from'/'to' dates.")
		}
		windowMs = toMs - fromMs
		granularityMs = AutoGranularity(windowMs)
		nowMs = toMs
		windowLabel = "custom"
		fromPtr = &opts.From
		toPtr = &opts.To
	} else {
		var err error
		windowMs, granularityMs, err = ParseTimelineWindow(windowKey)
		if err != nil {
			return nil, err
		}
		nowMs = time.Now().UnixMilli()
		windowLabel = windowKey
	}

	buckets := AggregateTimeline(jobs, nowMs, windowMs, granularityMs)
	return &Result{
		Window:        windowLabel,
		WindowMs:      windowMs,
		GranularityMs: granularityMs,
		From:          fromPtr,
		To:            toPtr,
		Buckets:       buckets,
		GeneratedAt:   time.Now().UTC().Format(time.RFC3339),
	}, nil
}

// parseTimeMs parses an ISO timestamp string and returns UnixMilli, or -1 on error.
func parseTimeMs(s string) int64 {
	return datetime.ParseStringMs(s)
}
