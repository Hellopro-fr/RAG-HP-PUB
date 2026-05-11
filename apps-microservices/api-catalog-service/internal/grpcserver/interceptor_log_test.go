package grpcserver

import (
	"bytes"
	"context"
	"log"
	"strings"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestLoggingInterceptor_LogsOKAndPeer(t *testing.T) {
	var buf bytes.Buffer
	old := log.Writer()
	log.SetOutput(&buf)
	defer log.SetOutput(old)

	inter := NewLoggingInterceptor()
	info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/ListServices"}
	handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
	if _, err := inter(context.Background(), nil, info, handler); err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, "ListServices") || !strings.Contains(out, "code=OK") {
		t.Fatalf("missing log fields: %q", out)
	}
}

func TestLoggingInterceptor_LogsError(t *testing.T) {
	var buf bytes.Buffer
	old := log.Writer()
	log.SetOutput(&buf)
	defer log.SetOutput(old)

	inter := NewLoggingInterceptor()
	info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/GetService"}
	handler := func(ctx context.Context, req any) (any, error) {
		return nil, status.Error(codes.NotFound, "nope")
	}
	_, _ = inter(context.Background(), nil, info, handler)
	if !strings.Contains(buf.String(), "code=NotFound") {
		t.Fatalf("missing code: %q", buf.String())
	}
}
