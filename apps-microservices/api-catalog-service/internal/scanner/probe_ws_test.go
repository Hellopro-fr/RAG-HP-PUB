package scanner

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestProbeAPIInfo_FullPayload(t *testing.T) {
	body := `{
      "service":"x","version":"1",
      "ws":  {"endpoints":[{"path":"/ws/a","summary":"A"},{"path":"/ws/b"}]},
      "grpc":{"address":"x:50051","reflection":true}
    }`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api-info" {
			http.NotFound(w, r)
			return
		}
		_, _ = w.Write([]byte(body))
	}))
	defer srv.Close()
	info := ProbeAPIInfo(context.Background(), srv.URL, time.Second)
	if info.GRPCAddress != "x:50051" || !info.GRPCReflection {
		t.Fatalf("grpc info wrong: %+v", info)
	}
	if len(info.WSEndpoints) != 2 || info.WSEndpoints[0].Path != "/ws/a" {
		t.Fatalf("ws wrong: %+v", info.WSEndpoints)
	}
}

func TestProbeAPIInfo_404_ReturnsZero(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(http.NotFound))
	defer srv.Close()
	info := ProbeAPIInfo(context.Background(), srv.URL, time.Second)
	if info.GRPCAddress != "" || len(info.WSEndpoints) != 0 {
		t.Fatalf("expect zero info, got %+v", info)
	}
}
