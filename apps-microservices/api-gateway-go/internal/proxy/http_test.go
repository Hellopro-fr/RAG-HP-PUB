package proxy

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func newProxyRouter(serviceMap map[string]string, timeouts map[string]float64, hist HistoryEnqueuer) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	h := NewHTTPHandler(HTTPDeps{
		ServiceMap:        serviceMap,
		DownstreamTimeout: timeouts,
		History:           hist,
	})
	r.Any("/:service/*path", h)
	return r
}

type fakeHist struct{ events []HistoryEvent }

func (f *fakeHist) Enqueue(e HistoryEvent) { f.events = append(f.events, e) }

func TestProxyForwardsAndAddsSecurityHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/foo/bar", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"ok":true}`)
	}))
	defer upstream.Close()

	r := newProxyRouter(map[string]string{"/svc-service": upstream.URL}, nil, &fakeHist{})
	req := httptest.NewRequest("GET", "/svc-service/foo/bar", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code)
	require.Equal(t, "nosniff", w.Header().Get("X-Content-Type-Options"))
	require.Equal(t, "DENY", w.Header().Get("X-Frame-Options"))
	require.Equal(t, "max-age=31536000; includeSubDomains", w.Header().Get("Strict-Transport-Security"))
	require.Contains(t, w.Body.String(), "ok")
}

func TestProxyUnknownService404(t *testing.T) {
	r := newProxyRouter(map[string]string{}, nil, &fakeHist{})
	req := httptest.NewRequest("GET", "/nope-service/x", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 404, w.Code)
	require.Contains(t, w.Body.String(), "Service not found")
}

func TestProxyTimeoutReturns504(t *testing.T) {
	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
	}))
	defer slow.Close()
	r := newProxyRouter(
		map[string]string{"/slow-service": slow.URL},
		map[string]float64{"slow-service": 0.01},
		&fakeHist{},
	)
	req := httptest.NewRequest("GET", "/slow-service/x", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	require.Equal(t, 504, w.Code)
	require.Contains(t, strings.ToLower(w.Body.String()), "timeout")
}
