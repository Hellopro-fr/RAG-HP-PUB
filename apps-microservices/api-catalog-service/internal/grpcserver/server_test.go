package grpcserver

import (
	"context"
	"encoding/json"
	"net"
	"reflect"
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

// newTestServer returns a *Server and the underlying *EndpointRepo built from
// the same in-memory SQLite DB. Use the returned repo to seed endpoint rows in
// tests that need direct DB access (e.g. UpdateEndpoint, HasEndpointOverrides).
func newTestServer(t *testing.T) (*Server, *repository.EndpointRepo) {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(g); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	sr := repository.NewServiceRepo(g)
	er := repository.NewEndpointRepo(g)
	srv := NewServer(Deps{Services: sr, Endpoints: er, AdminKey: "k"})
	return srv, er
}

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

func TestServer_CreateService_WithAuthPolicy(t *testing.T) {
	srv, _ := newTestServer(t)
	got, err := srv.CreateService(context.Background(), &pb.CreateServiceRequest{
		Name:        "alpha",
		BaseUrl:     "http://alpha",
		Protocols:   []pb.Protocol{pb.Protocol_REST},
		AuthPolicy:  pb.AuthPolicy_BEARER,
		PublicPaths: []string{"/health"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if got.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("auth_policy=%v; want BEARER", got.GetAuthPolicy())
	}
	if want := []string{"/health"}; !reflect.DeepEqual(got.GetPublicPaths(), want) {
		t.Fatalf("public_paths=%v; want %v", got.GetPublicPaths(), want)
	}
}

func TestServer_UpdateService_AuthPolicyOnly(t *testing.T) {
	srv, _ := newTestServer(t)
	created, _ := srv.CreateService(context.Background(), &pb.CreateServiceRequest{
		Name: "beta", BaseUrl: "http://beta", Protocols: []pb.Protocol{pb.Protocol_REST},
	})
	policy := pb.AuthPolicy_ADMIN_KEY
	updated, err := srv.UpdateService(context.Background(), &pb.UpdateServiceRequest{
		Id:         created.GetId(),
		AuthPolicy: &policy,
	})
	if err != nil {
		t.Fatal(err)
	}
	if updated.GetAuthPolicy() != pb.AuthPolicy_ADMIN_KEY {
		t.Fatalf("auth_policy=%v; want ADMIN_KEY", updated.GetAuthPolicy())
	}
}

func TestServer_UpdateEndpoint_SetThenClear(t *testing.T) {
	srv, er := newTestServer(t)
	created, _ := srv.CreateService(context.Background(), &pb.CreateServiceRequest{
		Name: "gamma", BaseUrl: "http://gamma", Protocols: []pb.Protocol{pb.Protocol_REST},
	})
	epRow := db.EndpointRow{ID: "ep-1", ServiceID: created.GetId(), Protocol: "rest", Path: "/x"}
	if err := er.ReplaceForService(created.GetId(), []db.EndpointRow{epRow}); err != nil {
		t.Fatalf("seed endpoint: %v", err)
	}

	bearer := pb.AuthPolicy_BEARER
	got, err := srv.UpdateEndpoint(context.Background(), &pb.UpdateEndpointRequest{Id: "ep-1", AuthPolicy: &bearer})
	if err != nil {
		t.Fatal(err)
	}
	if got.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("set: got=%v; want BEARER", got.GetAuthPolicy())
	}

	got2, err := srv.UpdateEndpoint(context.Background(), &pb.UpdateEndpointRequest{Id: "ep-1", AuthPolicy: nil})
	if err != nil {
		t.Fatal(err)
	}
	if got2.AuthPolicy != nil {
		t.Fatalf("clear: got=%v; want nil", got2.GetAuthPolicy())
	}
}

func TestServer_ListServices_HasEndpointOverrides(t *testing.T) {
	srv, er := newTestServer(t)
	a, _ := srv.CreateService(context.Background(), &pb.CreateServiceRequest{
		Name: "a", BaseUrl: "http://a", Protocols: []pb.Protocol{pb.Protocol_REST},
	})
	_, _ = srv.CreateService(context.Background(), &pb.CreateServiceRequest{
		Name: "b", BaseUrl: "http://b", Protocols: []pb.Protocol{pb.Protocol_REST},
	})
	policy := 2
	if err := er.ReplaceForService(a.GetId(), []db.EndpointRow{
		{ID: "ep-a", ServiceID: a.GetId(), Protocol: "rest", Path: "/", AuthPolicy: &policy},
	}); err != nil {
		t.Fatalf("seed endpoint: %v", err)
	}

	resp, err := srv.ListServices(context.Background(), &pb.ListServicesRequest{Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	var aHasOverrides, bNoOverrides bool
	for _, s := range resp.GetItems() {
		if s.GetName() == "a-service" {
			aHasOverrides = s.GetHasEndpointOverrides()
		}
		if s.GetName() == "b-service" {
			bNoOverrides = !s.GetHasEndpointOverrides()
		}
	}
	if !aHasOverrides || !bNoOverrides {
		t.Fatalf("expected a-service hasOverrides=true and b-service=false; got items=%v", resp.GetItems())
	}
}
