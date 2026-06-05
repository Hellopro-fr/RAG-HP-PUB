package api

import (
	"context"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"

	pb "account-service/internal/genproto/api_catalog"
)

type fakeCatalogServer struct{ pb.UnimplementedApiCatalogServer }

func (fakeCatalogServer) ListServices(ctx context.Context, _ *pb.ListServicesRequest) (*pb.ListServicesResponse, error) {
	return &pb.ListServicesResponse{Total: 1, Items: []*pb.Service{{Id: "a", Name: "n"}}}, nil
}

func (fakeCatalogServer) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) {
	return &pb.Endpoint{Id: req.GetId(), Path: "/updated"}, nil
}

func TestCatalogClient_List(t *testing.T) {
	lis := bufconn.Listen(1024 * 1024)
	s := grpc.NewServer()
	pb.RegisterApiCatalogServer(s, fakeCatalogServer{})
	go func() { _ = s.Serve(lis) }()
	defer s.Stop()

	conn, err := grpc.NewClient("passthrough://bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()

	cli := NewCatalogClient(conn, "")
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	resp, err := cli.ListServices(ctx, 10, 0, "")
	if err != nil {
		t.Fatal(err)
	}
	if resp.Total != 1 || resp.Items[0].Name != "n" {
		t.Fatalf("got %+v", resp)
	}
}

func TestCatalogClient_UpdateEndpoint(t *testing.T) {
	lis := bufconn.Listen(1024 * 1024)
	s := grpc.NewServer()
	pb.RegisterApiCatalogServer(s, fakeCatalogServer{})
	go func() { _ = s.Serve(lis) }()
	defer s.Stop()

	conn, err := grpc.NewClient("passthrough://bufnet",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()

	cli := NewCatalogClient(conn, "test-admin-key")
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	ep, err := cli.UpdateEndpoint(ctx, &pb.UpdateEndpointRequest{Id: "ep-42"})
	if err != nil {
		t.Fatal(err)
	}
	if ep.GetId() != "ep-42" {
		t.Fatalf("expected id ep-42, got %q", ep.GetId())
	}
}
