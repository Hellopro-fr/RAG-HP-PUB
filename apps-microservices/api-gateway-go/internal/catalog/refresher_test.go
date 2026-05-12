package catalog

import (
	"context"
	"net"
	"sync/atomic"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"

	pb "api-gateway-go/internal/genproto/api_catalog"
)

type stubServer struct {
	pb.UnimplementedApiCatalogServer
	calls int32
}

func (s *stubServer) ListServices(ctx context.Context, _ *pb.ListServicesRequest) (*pb.ListServicesResponse, error) {
	atomic.AddInt32(&s.calls, 1)
	return &pb.ListServicesResponse{Items: []*pb.Service{
		{Name: "foo-service", BaseUrl: "http://foo:8000", Status: pb.Status_ACTIVE},
		{Name: "bar-service", BaseUrl: "http://bar:8000", Status: pb.Status_DEPRECATED},
	}, Total: 2}, nil
}

func startBuf(t *testing.T) (*grpc.ClientConn, *stubServer, func()) {
	t.Helper()
	lis := bufconn.Listen(1024 * 1024)
	s := grpc.NewServer()
	stub := &stubServer{}
	pb.RegisterApiCatalogServer(s, stub)
	go func() { _ = s.Serve(lis) }()
	conn, err := grpc.NewClient("passthrough://bufnet",
		grpc.WithContextDialer(func(_ context.Context, _ string) (net.Conn, error) { return lis.Dial() }),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	return conn, stub, func() { conn.Close(); s.Stop() }
}

func TestClient_BuildMap_FiltersInactive(t *testing.T) {
	conn, _, stop := startBuf(t)
	defer stop()
	cli := NewClient(conn)
	m, err := cli.BuildMap(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got := m["/foo-service"]; got != "http://foo:8000" {
		t.Fatalf("active route missing: %+v", m)
	}
	if _, has := m["/bar-service"]; has {
		t.Fatal("deprecated route should be filtered out")
	}
}

func TestRefresher_BootstrapFallsBackToEnvOnEmpty(t *testing.T) {
	// No server bound — dial would normally fail. We use an unreachable conn target.
	conn, _ := grpc.NewClient("passthrough://nowhere",
		grpc.WithContextDialer(func(_ context.Context, _ string) (net.Conn, error) {
			return nil, context.DeadlineExceeded
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()))
	cli := NewClient(conn)
	fallback := map[string]string{"/legacy-service": "http://legacy:9999"}
	r := NewRefresher(cli, time.Hour, fallback)
	m, src := r.Bootstrap(context.Background(), 200*time.Millisecond)
	if src != "env" {
		t.Fatalf("source = %q, want env", src)
	}
	if m["/legacy-service"] != "http://legacy:9999" {
		t.Fatalf("fallback not applied: %+v", m)
	}
}

func TestRefresher_BootstrapUsesCatalog(t *testing.T) {
	conn, _, stop := startBuf(t)
	defer stop()
	cli := NewClient(conn)
	r := NewRefresher(cli, time.Hour, map[string]string{"/legacy-service": "x"})
	m, src := r.Bootstrap(context.Background(), 2*time.Second)
	if src != "catalog" {
		t.Fatalf("source = %q, want catalog", src)
	}
	if _, has := m["/legacy-service"]; has {
		t.Fatal("env fallback should not be present when catalog succeeded")
	}
	if m["/foo-service"] != "http://foo:8000" {
		t.Fatalf("foo-service missing: %+v", m)
	}
}
