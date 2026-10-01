package grpcserver

import (
	"context"
	"strings"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

var writeMethods = map[string]struct{}{
	"/api_catalog.ApiCatalog/CreateService": {},
	"/api_catalog.ApiCatalog/UpdateService": {},
	"/api_catalog.ApiCatalog/DeleteService": {},
	"/api_catalog.ApiCatalog/RescanAll":     {},
	"/api_catalog.ApiCatalog/RescanService": {},
}

func NewAdminInterceptor(adminKey string) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if _, write := writeMethods[info.FullMethod]; !write {
			return handler(ctx, req)
		}
		if adminKey == "" {
			return nil, status.Error(codes.Unauthenticated, "admin key not configured")
		}
		md, _ := metadata.FromIncomingContext(ctx)
		vals := md.Get("authorization")
		if len(vals) == 0 {
			return nil, status.Error(codes.Unauthenticated, "missing authorization metadata")
		}
		h := vals[0]
		if !strings.HasPrefix(h, "Bearer ") || strings.TrimPrefix(h, "Bearer ") != adminKey {
			return nil, status.Error(codes.Unauthenticated, "invalid admin key")
		}
		return handler(ctx, req)
	}
}
