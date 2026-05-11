package proxy

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
)

func TestHistoryWorkerSanitizes(t *testing.T) {
	gdb, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, dbpkg.AutoMigrate(gdb))
	w := NewHistoryWorker(gdb, map[string]struct{}{"crawling-service": {}}, 16, 1)
	w.Start()
	defer w.Stop()

	w.Enqueue(HistoryEvent{
		ServiceName: "ok",
		Method:      "GET",
		Path:        "/p",
		StatusCode:  200,
		ClientIP:    "1.1.1.1",
		RequestHeaders: map[string]string{
			"Authorization": "Bearer x",
			"User-Agent":    "ua",
		},
		DurationMs: 12,
	})
	w.Enqueue(HistoryEvent{
		ServiceName: "crawling-service",
		Method:      "GET",
		Path:        "/p",
		StatusCode:  200,
		ClientIP:    "1.1.1.1",
		DurationMs:  1,
	})

	require.Eventually(t, func() bool {
		var n int64
		_ = gdb.Model(&dbpkg.ApiCallHistory{}).Count(&n).Error
		return n == 1
	}, 2*time.Second, 20*time.Millisecond)

	var row dbpkg.ApiCallHistory
	require.NoError(t, gdb.First(&row).Error)
	require.NotNil(t, row.RequestHeaders)
	require.Contains(t, *row.RequestHeaders, "[REDACTED]")
	require.NotContains(t, *row.RequestHeaders, "Bearer x")
}
