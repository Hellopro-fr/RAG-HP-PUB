package grpcserver

import (
	"context"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func TestAdminInterceptor_AllowsReadWithoutKey(t *testing.T) {
	inter := NewAdminInterceptor("secret")
	info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/ListServices"}
	handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
	out, err := inter(context.Background(), nil, info, handler)
	if err != nil || out != "ok" {
		t.Fatalf("read without key should pass; got %v err=%v", out, err)
	}
}

func TestAdminInterceptor_BlocksWriteWithoutKey(t *testing.T) {
	inter := NewAdminInterceptor("secret")
	info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/CreateService"}
	handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
	_, err := inter(context.Background(), nil, info, handler)
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("want Unauthenticated, got %v", err)
	}
}

func TestAdminInterceptor_AllowsWriteWithKey(t *testing.T) {
	inter := NewAdminInterceptor("secret")
	md := metadata.New(map[string]string{"authorization": "Bearer secret"})
	ctx := metadata.NewIncomingContext(context.Background(), md)
	info := &grpc.UnaryServerInfo{FullMethod: "/api_catalog.ApiCatalog/CreateService"}
	handler := func(ctx context.Context, req any) (any, error) { return "ok", nil }
	out, err := inter(ctx, nil, info, handler)
	if err != nil || out != "ok" {
		t.Fatalf("write with key should pass; got %v err=%v", out, err)
	}
}
