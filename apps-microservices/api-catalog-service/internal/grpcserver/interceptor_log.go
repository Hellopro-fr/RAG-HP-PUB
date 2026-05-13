package grpcserver

import (
	"context"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/peer"
	"google.golang.org/grpc/status"
)

// NewLoggingInterceptor logs every unary RPC: method, peer, status code,
// duration. Use to confirm callers are reaching the catalog.
func NewLoggingInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		start := time.Now()
		resp, err := handler(ctx, req)
		code := status.Code(err).String()
		addr := "?"
		if p, ok := peer.FromContext(ctx); ok && p.Addr != nil {
			addr = p.Addr.String()
		}
		log.Printf("rpc method=%s peer=%s code=%s dur=%s", info.FullMethod, addr, code, time.Since(start))
		return resp, err
	}
}
