// Package capacityplanning aggregates per-replica heartbeats to answer
// "can we reduce RAM per replica and run more of them?".
//
// Mirrors src/lib/capacityPlanning.js exactly (same field names + sort order).
package capacityplanning

import (
	"errors"
	"sort"
)

// WindowMap maps frontend window keys to milliseconds.
var WindowMap = map[string]int64{
	"1h":  60 * 60 * 1000,
	"24h": 24 * 60 * 60 * 1000,
	"7d":  7 * 24 * 60 * 60 * 1000,
}

func ParseWindow(key string) (int64, error) {
	ms, ok := WindowMap[key]
	if !ok {
		return 0, errors.New("Invalid window. Use '1h', '24h' or '7d'.")
	}
	return ms, nil
}

// Sample is one heartbeat measurement (cpu/ram) for a replica at ts ms.
type Sample struct {
	Ts       int64
	CPU      float64
	RAM      float64
	TotalRAM float64
	JobID    string
}

// ReplicaStats is the per-replica aggregated view returned to the UI.
type ReplicaStats struct {
	ReplicaID   string  `json:"replicaId"`
	Allocated   float64 `json:"allocated"`
	Peak        float64 `json:"peak"`
	PeakTs      int64   `json:"peak_ts"`
	PeakJobID   *string `json:"peak_job_id"`
	Avg         float64 `json:"avg"`
	SampleCount int     `json:"sample_count"`
	LastSeen    int64   `json:"last_seen"`
	Efficiency  float64 `json:"efficiency"`
}

// Totals is the cross-replica summary.
type Totals struct {
	ReplicaCount    int     `json:"replica_count"`
	TotalAllocated  float64 `json:"total_allocated"`
	TotalPeakWorst  float64 `json:"total_peak_worst"`
	TotalAvg        float64 `json:"total_avg"`
	Waste           float64 `json:"waste"`
	WastePct        float64 `json:"waste_pct"`
	Efficiency      float64 `json:"efficiency"`
}

// AggregateByReplica folds per-replica points into ReplicaStats sorted by peak desc.
func AggregateByReplica(pointsByReplica map[string][]Sample) []ReplicaStats {
	out := make([]ReplicaStats, 0, len(pointsByReplica))
	for id, points := range pointsByReplica {
		if len(points) == 0 {
			continue
		}
		var allocated, peak, sum float64
		var peakTs, lastTs int64
		var peakJobID *string
		for _, p := range points {
			if p.TotalRAM > allocated {
				allocated = p.TotalRAM
			}
			if p.RAM > peak {
				peak = p.RAM
				peakTs = p.Ts
				if p.JobID != "" {
					j := p.JobID
					peakJobID = &j
				} else {
					peakJobID = nil
				}
			}
			sum += p.RAM
			if p.Ts > lastTs {
				lastTs = p.Ts
			}
		}
		avg := sum / float64(len(points))
		eff := 0.0
		if allocated > 0 {
			eff = peak / allocated
		}
		out = append(out, ReplicaStats{
			ReplicaID:   id,
			Allocated:   allocated,
			Peak:        peak,
			PeakTs:      peakTs,
			PeakJobID:   peakJobID,
			Avg:         avg,
			SampleCount: len(points),
			LastSeen:    lastTs,
			Efficiency:  eff,
		})
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Peak > out[j].Peak })
	return out
}

// ComputeTotals folds the per-replica stats into a single summary.
func ComputeTotals(replicas []ReplicaStats) Totals {
	var totAlloc, totPeak, totAvg float64
	for _, r := range replicas {
		totAlloc += r.Allocated
		totPeak += r.Peak
		totAvg += r.Avg
	}
	waste := totAlloc - totPeak
	wastePct := 0.0
	eff := 0.0
	if totAlloc > 0 {
		wastePct = waste / totAlloc
		eff = totPeak / totAlloc
	}
	return Totals{
		ReplicaCount:   len(replicas),
		TotalAllocated: totAlloc,
		TotalPeakWorst: totPeak,
		TotalAvg:       totAvg,
		Waste:          waste,
		WastePct:       wastePct,
		Efficiency:     eff,
	}
}
