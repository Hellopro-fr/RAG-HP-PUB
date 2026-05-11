package catalog

import (
	"context"

	"google.golang.org/grpc"

	pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/genproto/api_catalog"
)

// Client wraps the generated gRPC ApiCatalog client.
type Client struct{ cli pb.ApiCatalogClient }

// NewClient constructs a Client from an existing gRPC connection.
func NewClient(conn *grpc.ClientConn) *Client { return &Client{cli: pb.NewApiCatalogClient(conn)} }

// BuildMap returns prefix -> base_url for ACTIVE services only.
// Prefix is "/" + service.Name (which already includes the "-service" suffix).
func (c *Client) BuildMap(ctx context.Context) (map[string]string, error) {
	resp, err := c.cli.ListServices(ctx, &pb.ListServicesRequest{Limit: 1000})
	if err != nil {
		return nil, err
	}
	out := make(map[string]string, len(resp.GetItems()))
	for _, s := range resp.GetItems() {
		if s.GetStatus() != pb.Status_ACTIVE {
			continue
		}
		out["/"+s.GetName()] = s.GetBaseUrl()
	}
	return out, nil
}
