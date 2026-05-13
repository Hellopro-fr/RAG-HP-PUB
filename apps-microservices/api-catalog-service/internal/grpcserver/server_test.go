package grpcserver

import (
	"context"
	"encoding/json"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"api-catalog-service/internal/db"
	pb "api-catalog-service/internal/genproto/api_catalog"
	"api-catalog-service/internal/repository"
)

func startBufServer(t *testing.T) (pb.ApiCatalogClient, func()) {
	t.Helper()
	g, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	_ = db.AutoMigrate(g)
	sr := repository.NewServiceRepo(g)
	er := repository.NewEndpointRepo(g)
	p, _ := json.Marshal([]string{"rest"})
	_ = sr.Create(&db.ServiceRow{ID: "s1", Name: "foo-service", BaseURL: "http://x", Protocols: string(p), Source: "env", Status: "active"})

	lis := bufconn.Listen(1024 * 1024)
	s := grpc.NewServer()
	pb.RegisterApiCatalogServer(s, NewServer(Deps{Services: sr, Endpoints: er, AdminKey: "k"}))
	go func() { _ = s.Serve(lis) }()

	conn, err := grpc.NewClient("passthrough://bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	return pb.NewApiCatalogClient(conn), func() { conn.Close(); s.Stop() }
}

func TestServer_ListServices_ReturnsSeeded(t *testing.T) {
	cli, stop := startBufServer(t)
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	resp, err := cli.ListServices(ctx, &pb.ListServicesRequest{Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if resp.Total != 1 || resp.Items[0].Name != "foo-service" {
		t.Fatalf("got %+v", resp)
	}
}

func TestServer_GetService_NotFound(t *testing.T) {
	cli, stop := startBufServer(t)
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_, err := cli.GetService(ctx, &pb.GetServiceRequest{Id: "does-not-exist"})
	if err == nil {
		t.Fatal("expected error for missing service")
	}
}

func TestServer_GetService_Found(t *testing.T) {
	cli, stop := startBufServer(t)
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	svc, err := cli.GetService(ctx, &pb.GetServiceRequest{Id: "s1"})
	if err != nil {
		t.Fatal(err)
	}
	if svc.Name != "foo-service" {
		t.Fatalf("got name %q", svc.Name)
	}
}

func TestServer_ListEndpoints_Empty(t *testing.T) {
	cli, stop := startBufServer(t)
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	resp, err := cli.ListEndpoints(ctx, &pb.ListEndpointsRequest{ServiceId: "s1"})
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 0 {
		t.Fatalf("expected empty, got %d", len(resp.Items))
	}
}
