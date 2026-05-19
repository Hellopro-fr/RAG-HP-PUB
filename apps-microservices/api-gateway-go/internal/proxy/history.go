package proxy

import (
	"encoding/json"
	"log"
	"strings"
	"sync"

	"gorm.io/gorm"

	dbpkg "api-gateway-go/internal/db"
)

var sensitiveHeaders = map[string]struct{}{
	"authorization": {}, "cookie": {}, "x-api-key": {}, "set-cookie": {},
}

// HistoryEvent holds the data to be persisted for a single proxied request.
type HistoryEvent struct {
	ServiceName    string
	Method         string
	Path           string
	StatusCode     int
	ClientIP       string
	RequestHeaders map[string]string
	DurationMs     int
}

// HistoryWorker asynchronously persists proxied request events to the database.
// Excluded service names are dropped without persisting.
type HistoryWorker struct {
	db       *gorm.DB
	excluded map[string]struct{}
	ch       chan HistoryEvent
	workers  int
	wg       sync.WaitGroup
	stopOnce sync.Once
}

// NewHistoryWorker creates a HistoryWorker with the given DB, excluded services,
// channel buffer size, and number of parallel writer goroutines.
func NewHistoryWorker(g *gorm.DB, excluded map[string]struct{}, buffer, workers int) *HistoryWorker {
	if workers < 1 {
		workers = 1
	}
	return &HistoryWorker{
		db:       g,
		excluded: excluded,
		ch:       make(chan HistoryEvent, buffer),
		workers:  workers,
	}
}

// Start launches the background writer goroutines.
func (h *HistoryWorker) Start() {
	for i := 0; i < h.workers; i++ {
		h.wg.Add(1)
		go h.run()
	}
}

// Stop drains the queue and waits for all writers to finish.
// Safe to call multiple times.
func (h *HistoryWorker) Stop() {
	h.stopOnce.Do(func() {
		close(h.ch)
		h.wg.Wait()
	})
}

// Enqueue submits an event for async persistence.
// If the buffer is full, the event is dropped and a warning is logged.
func (h *HistoryWorker) Enqueue(e HistoryEvent) {
	select {
	case h.ch <- e:
	default:
		log.Printf("[history] queue full, dropping event for service=%s path=%s", e.ServiceName, e.Path)
	}
}

func (h *HistoryWorker) run() {
	defer h.wg.Done()
	for e := range h.ch {
		if _, skip := h.excluded[e.ServiceName]; skip {
			continue
		}
		safe := sanitizeHeaders(e.RequestHeaders)
		raw, _ := json.Marshal(safe)
		s := string(raw)
		duration := e.DurationMs
		row := dbpkg.ApiCallHistory{
			ServiceName:    e.ServiceName,
			Method:         e.Method,
			Path:           e.Path,
			StatusCode:     e.StatusCode,
			ClientIP:       e.ClientIP,
			RequestHeaders: &s,
			DurationMs:     &duration,
		}
		if err := h.db.Create(&row).Error; err != nil {
			log.Printf("[history] insert failed service=%s path=%s err=%v", e.ServiceName, e.Path, err)
		}
	}
}

// sanitizeHeaders returns a copy of the header map with sensitive values replaced by [REDACTED].
func sanitizeHeaders(in map[string]string) map[string]string {
	out := make(map[string]string, len(in))
	for k, v := range in {
		if _, sensitive := sensitiveHeaders[strings.ToLower(k)]; sensitive {
			out[k] = "[REDACTED]"
		} else {
			out[k] = v
		}
	}
	return out
}
