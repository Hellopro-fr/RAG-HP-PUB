// Package imageproxy proxies HTTP requests to image-download-service.
//
// Connection: close — image-download-service runs in many replicas (20+ in
// prod). Default keep-alive caches sockets to specific replica IPs; when a
// replica scales down, its cached socket fails ECONNREFUSED. We force a fresh
// connection per request so DNS round-robin picks a healthy replica each time.
// Cost: ~1ms TCP setup, negligible vs FS NFS latency.
package imageproxy

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"syscall"
	"time"
)

const DefaultTimeout = 60 * time.Second

func defaultBaseURL() string {
	if v := os.Getenv("IMAGE_DOWNLOAD_SERVICE_URL"); v != "" {
		return v
	}
	return "http://image-download-service:8505"
}

type Options struct {
	Method   string
	Path     string
	BaseURL  string
	Timeout  time.Duration
	Client   *http.Client // injectable for tests
}

type Result struct {
	Status      int
	Body        []byte
	ContentType string
}

func Forward(ctx context.Context, query url.Values, body io.Reader, opts Options) *Result {
	timeout := opts.Timeout
	if timeout == 0 {
		timeout = DefaultTimeout
	}
	base := opts.BaseURL
	if base == "" {
		base = defaultBaseURL()
	}

	rawURL := base + opts.Path
	if len(query) > 0 {
		rawURL += "?" + query.Encode()
	}

	reqCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(reqCtx, opts.Method, rawURL, body)
	if err != nil {
		return jsonResult(502, `{"error":"upstream proxy error","message":"`+err.Error()+`"}`)
	}
	req.Header.Set("Connection", "close")
	if body != nil && (opts.Method == "POST" || opts.Method == "PUT" || opts.Method == "PATCH") {
		req.Header.Set("Content-Type", "application/json")
	}

	client := opts.Client
	if client == nil {
		client = &http.Client{Transport: &http.Transport{DisableKeepAlives: true}}
	}

	resp, err := client.Do(req)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
			return jsonResult(504, `{"error":"upstream timeout","service":"image-download-service"}`)
		}
		if isUnreachable(err) {
			return jsonResult(503, `{"error":"image-download-service unreachable","code":"`+errCode(err)+`"}`)
		}
		return jsonResult(502, `{"error":"upstream proxy error","message":"`+err.Error()+`"}`)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 204 {
		return &Result{Status: 204}
	}
	b, _ := io.ReadAll(resp.Body)
	return &Result{
		Status:      resp.StatusCode,
		Body:        b,
		ContentType: resp.Header.Get("Content-Type"),
	}
}

func jsonResult(status int, body string) *Result {
	return &Result{Status: status, Body: []byte(body), ContentType: "application/json; charset=utf-8"}
}

func isUnreachable(err error) bool {
	if err == nil {
		return false
	}
	s := err.Error()
	if strings.Contains(s, "connection refused") || strings.Contains(s, "no such host") || strings.Contains(s, "EAI_AGAIN") {
		return true
	}
	var sysErr syscall.Errno
	if errors.As(err, &sysErr) {
		return sysErr == syscall.ECONNREFUSED || sysErr == syscall.EHOSTUNREACH || sysErr == syscall.ENETUNREACH
	}
	return false
}

func errCode(err error) string {
	s := err.Error()
	if strings.Contains(s, "connection refused") {
		return "ECONNREFUSED"
	}
	if strings.Contains(s, "no such host") {
		return "ENOTFOUND"
	}
	return "UNKNOWN"
}
