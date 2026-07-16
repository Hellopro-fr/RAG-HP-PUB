package api

import (
	"context"

	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"

	pb "account-service/internal/genproto/api_catalog"
)

type CatalogClient struct {
	cli      pb.ApiCatalogClient
	adminKey string
}

func NewCatalogClient(conn *grpc.ClientConn, adminKey string) *CatalogClient {
	return &CatalogClient{cli: pb.NewApiCatalogClient(conn), adminKey: adminKey}
}

func (c *CatalogClient) authCtx(ctx context.Context) context.Context {
	if c.adminKey == "" {
		return ctx
	}
	return metadata.AppendToOutgoingContext(ctx, "authorization", "Bearer "+c.adminKey)
}

func (c *CatalogClient) ListServices(ctx context.Context, limit, offset int, filter string) (*pb.ListServicesResponse, error) {
	return c.cli.ListServices(ctx, &pb.ListServicesRequest{Limit: int32(limit), Offset: int32(offset), Filter: filter})
}

func (c *CatalogClient) GetService(ctx context.Context, id string) (*pb.Service, error) {
	return c.cli.GetService(ctx, &pb.GetServiceRequest{Id: id})
}

func (c *CatalogClient) ListEndpoints(ctx context.Context, serviceID string, protocol pb.Protocol) (*pb.ListEndpointsResponse, error) {
	return c.cli.ListEndpoints(ctx, &pb.ListEndpointsRequest{ServiceId: serviceID, Protocol: protocol})
}

func (c *CatalogClient) Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) {
	return c.cli.CreateService(c.authCtx(ctx), req)
}

func (c *CatalogClient) Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) {
	return c.cli.UpdateService(c.authCtx(ctx), req)
}

func (c *CatalogClient) Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error) {
	return c.cli.DeleteService(c.authCtx(ctx), &pb.DeleteServiceRequest{Id: id})
}

func (c *CatalogClient) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) {
	return c.cli.UpdateEndpoint(c.authCtx(ctx), req)
}

func (c *CatalogClient) RescanAll(ctx context.Context) (*pb.RescanReport, error) {
	return c.cli.RescanAll(c.authCtx(ctx), &pb.RescanAllRequest{})
}

func (c *CatalogClient) RescanService(ctx context.Context, id string) (*pb.RescanReport, error) {
	return c.cli.RescanService(c.authCtx(ctx), &pb.RescanServiceRequest{Id: id})
}
