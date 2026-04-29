package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/imageproxy"
)

func TestImageProxy_Forward200JSON(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/domains/_summary" {
			t.Errorf("path = %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer upstream.Close()

	res := imageproxy.Forward(context.Background(), nil, nil, imageproxy.Options{
		Method:  "GET",
		Path:    "/domains/_summary",
		BaseURL: upstream.URL,
	})
	if res.Status != 200 {
		t.Errorf("status = %d", res.Status)
	}
	if !strings.Contains(string(res.Body), `"ok":true`) {
		t.Errorf("body = %s", res.Body)
	}
}

func TestImageProxy_Forward404(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(404)
		_, _ = w.Write([]byte(`{"detail":"not found"}`))
	}))
	defer upstream.Close()

	res := imageproxy.Forward(context.Background(), nil, nil, imageproxy.Options{
		Method:  "GET",
		Path:    "/domains/x/products",
		BaseURL: upstream.URL,
	})
	if res.Status != 404 {
		t.Errorf("status = %d", res.Status)
	}
	var body map[string]any
	_ = json.Unmarshal(res.Body, &body)
	if body["detail"] != "not found" {
		t.Errorf("body = %v", body)
	}
}

func TestImageProxy_503OnUnreachable(t *testing.T) {
	res := imageproxy.Forward(context.Background(), nil, nil, imageproxy.Options{
		Method:  "GET",
		Path:    "/x",
		BaseURL: "http://127.0.0.1:1", // port refused
		Timeout: 2 * time.Second,
	})
	if res.Status != 503 {
		t.Errorf("status = %d, want 503", res.Status)
	}
	if !strings.Contains(string(res.Body), "unreachable") {
		t.Errorf("body = %s", res.Body)
	}
}

func TestImageProxy_504OnTimeout(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(500 * time.Millisecond)
	}))
	defer upstream.Close()

	res := imageproxy.Forward(context.Background(), nil, nil, imageproxy.Options{
		Method:  "GET",
		Path:    "/x",
		BaseURL: upstream.URL,
		Timeout: 50 * time.Millisecond,
	})
	if res.Status != 504 {
		t.Errorf("status = %d, want 504", res.Status)
	}
}

func TestImageProxy_ForwardsQuery(t *testing.T) {
	var captured string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		captured = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer upstream.Close()

	q := url.Values{}
	q.Set("q", "test")
	q.Set("page", "2")
	imageproxy.Forward(context.Background(), q, nil, imageproxy.Options{
		Method: "GET", Path: "/domains/x/products", BaseURL: upstream.URL,
	})
	if !strings.Contains(captured, "q=test") || !strings.Contains(captured, "page=2") {
		t.Errorf("query = %q", captured)
	}
}

func TestImageProxy_ForwardsBodyOnPOST(t *testing.T) {
	var capturedBody []byte
	var capturedCT string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedBody, _ = io.ReadAll(r.Body)
		capturedCT = r.Header.Get("Content-Type")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer upstream.Close()

	imageproxy.Forward(context.Background(), nil, bytes.NewBufferString(`{"foo":"bar"}`), imageproxy.Options{
		Method: "POST", Path: "/sync/x", BaseURL: upstream.URL,
	})
	if string(capturedBody) != `{"foo":"bar"}` {
		t.Errorf("body = %s", capturedBody)
	}
	if capturedCT != "application/json" {
		t.Errorf("content-type = %s", capturedCT)
	}
}

func TestImageProxy_204NoContent(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(204)
	}))
	defer upstream.Close()

	res := imageproxy.Forward(context.Background(), nil, nil, imageproxy.Options{
		Method: "DELETE", Path: "/products/x/1", BaseURL: upstream.URL,
	})
	if res.Status != 204 {
		t.Errorf("status = %d", res.Status)
	}
	if len(res.Body) != 0 {
		t.Errorf("body = %v, want empty", res.Body)
	}
}
