// Package replicahistory provides per-replica CPU/RAM history helpers.
//
// The crawler-service publishes heartbeats every 2s to Redis sorted sets:
//
//	key:   replica:history:<replicaId>  (sorted set, score = ts ms)
//	value: { ts, cpu, ram, totalRam, jobId }
//
// Auto-trimmed to a 1h sliding window (1800 points/h max).
// The known-replica set tracks active replicas for batch endpoint.
package replicahistory

import (
	"errors"
)

// Window constants mirror JS WINDOW_MAP.
const (
	Window15m = int64(15 * 60 * 1000) // 15 minutes in ms
	Window1h  = int64(60 * 60 * 1000) // 1 hour in ms
)

var windowMap = map[string]int64{
	"15m": Window15m,
	"1h":  Window1h,
}

// ParseReplicaWindow parses a window string ("15m" or "1h") and returns the
// corresponding duration in milliseconds. Returns an error for any other value.
func ParseReplicaWindow(input string) (int64, error) {
	ms, ok := windowMap[input]
	if !ok {
		return 0, errors.New("Invalid window. Use '15m' or '1h'.")
	}
	return ms, nil
}

// HeartbeatSample is a compact metric sample persisted per heartbeat.
type HeartbeatSample struct {
	Ts       int64   `json:"ts"`
	CPU      float64 `json:"cpu"`
	RAM      float64 `json:"ram"`
	TotalRAM float64 `json:"totalRam"`
	JobID    *string `json:"jobId"`
}
