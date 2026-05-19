package scanner

import (
	"context"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/reflection"
)

func startReflectionServer(t *testing.T) (string, func()) {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	srv := grpc.NewServer()
	reflection.Register(srv)
	go func() { _ = srv.Serve(lis) }()
	return lis.Addr().String(), func() { srv.Stop() }
}

func TestProbeGRPC_ListsReflectionService(t *testing.T) {
	addr, stop := startReflectionServer(t)
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	eps, err := ProbeGRPC(ctx, addr, time.Second, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, e := range eps {
		if e.Path == "grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo" ||
			e.Path == "grpc.reflection.v1.ServerReflection/ServerReflectionInfo" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected reflection RPC in endpoint list, got %+v", eps)
	}
}
