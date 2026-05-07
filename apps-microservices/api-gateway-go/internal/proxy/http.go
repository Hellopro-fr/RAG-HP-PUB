package proxy

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

var excludedReqHeaders = map[string]struct{}{
	"host": {}, "content-length": {}, "transfer-encoding": {}, "connection": {},
}

var excludedRespHeaders = map[string]struct{}{
	"transfer-encoding": {}, "connection": {}, "content-length": {},
}

// HistoryEnqueuer abstracts async persistence of proxied request events.
// Production wires *HistoryWorker; tests inject a fake.
type HistoryEnqueuer interface {
	Enqueue(e HistoryEvent)
}

// HTTPDeps holds the dependencies for the HTTP reverse proxy handler.
type HTTPDeps struct {
	ServiceMap        map[string]string
	DownstreamTimeout map[string]float64
	History           HistoryEnqueuer
}

// NewHTTPHandler returns a Gin handler that reverse-proxies requests to downstream
// services based on the service segment of the URL path.
//
// Route pattern: /:service/*path
//   - service must match a key in ServiceMap (prefixed with "/")
//   - per-service timeouts are looked up in DownstreamTimeout by service name
//   - security headers are injected on every response
//   - every proxied request is enqueued in History (if non-nil)
func NewHTTPHandler(d HTTPDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		service := c.Param("service")
		path := strings.TrimPrefix(c.Param("path"), "/")

		baseURL, ok := d.ServiceMap["/"+service]
		if !ok {
			c.JSON(404, gin.H{"detail": "Service not found"})
			return
		}

		target := strings.TrimRight(baseURL, "/") + "/" + path
		if c.Request.URL.RawQuery != "" {
			target += "?" + c.Request.URL.RawQuery
		}

		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}

		req, err := http.NewRequestWithContext(c.Request.Context(), c.Request.Method, target, bytes.NewReader(body))
		if err != nil {
			c.JSON(500, gin.H{"detail": err.Error()})
			return
		}
		for k, vs := range c.Request.Header {
			if _, skip := excludedReqHeaders[strings.ToLower(k)]; skip {
				continue
			}
			for _, v := range vs {
				req.Header.Add(k, v)
			}
		}

		client, totalTimeout := clientForService(service, d.DownstreamTimeout)

		start := time.Now()
		resp, err := client.Do(req)
		durationMs := int(time.Since(start) / time.Millisecond)
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) || isTimeoutErr(err) {
				c.JSON(504, gin.H{"detail": fmt.Sprintf("Le service '%s' a depasse son timeout (%vs).", service, totalTimeout.Seconds())})
			} else {
				c.JSON(503, gin.H{"detail": fmt.Sprintf("Le service '%s' est indisponible.", service)})
			}
			return
		}
		defer resp.Body.Close()

		respBody, _ := io.ReadAll(resp.Body)

		for k, vs := range resp.Header {
			if _, skip := excludedRespHeaders[strings.ToLower(k)]; skip {
				continue
			}
			for _, v := range vs {
				c.Writer.Header().Add(k, v)
			}
		}
		c.Writer.Header().Set("X-Content-Type-Options", "nosniff")
		c.Writer.Header().Set("X-Frame-Options", "DENY")
		c.Writer.Header().Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		c.Writer.WriteHeader(resp.StatusCode)
		_, _ = c.Writer.Write(respBody)

		if d.History != nil {
			headers := make(map[string]string, len(c.Request.Header))
			for k, vs := range c.Request.Header {
				if len(vs) > 0 {
					headers[k] = vs[0]
				}
			}
			d.History.Enqueue(HistoryEvent{
				ServiceName:    resolveServiceName(c, service),
				Method:         c.Request.Method,
				Path:           c.Request.URL.Path,
				StatusCode:     resp.StatusCode,
				ClientIP:       c.ClientIP(),
				RequestHeaders: headers,
				DurationMs:     durationMs,
			})
		}
	}
}

// clientForService builds an http.Client with the configured per-service timeout.
// Services not in the timeout map get an unlimited client (timeout=0).
func clientForService(service string, timeouts map[string]float64) (*http.Client, time.Duration) {
	serviceKey := service
	if !strings.HasSuffix(service, "-service") {
		serviceKey = service + "-service"
	}

	t, ok := timeouts[serviceKey]
	if !ok {
		return &http.Client{}, 0
	}

	totalTimeout := time.Duration(t * float64(time.Second))
	client := &http.Client{
		Timeout: totalTimeout,
		Transport: &http.Transport{
			DialContext: (&net.Dialer{Timeout: 10 * time.Second}).DialContext,
		},
	}
	return client, totalTimeout
}

// resolveServiceName extracts the subject claim from a JWT payload stored in
// the Gin context (set by auth middleware), falling back to the raw service name.
func resolveServiceName(c *gin.Context, fallback string) string {
	v, ok := c.Get("token_payload")
	if !ok {
		return fallback
	}
	m, ok := v.(gin.H)
	if !ok {
		return fallback
	}
	sub, ok := m["sub"].(string)
	if !ok || sub == "" {
		return fallback
	}
	return sub
}

// isTimeoutErr reports whether err wraps a net timeout error.
func isTimeoutErr(err error) bool {
	type timeoutErr interface{ Timeout() bool }
	var te timeoutErr
	return errors.As(err, &te) && te.Timeout()
}
