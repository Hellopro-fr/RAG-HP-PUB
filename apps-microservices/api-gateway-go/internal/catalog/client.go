package catalog

import (
	"context"

	"google.golang.org/grpc"

	auth_pkg "api-gateway-go/internal/auth"
	pb "api-gateway-go/internal/genproto/api_catalog"
)

// Client wraps the generated gRPC ApiCatalog client.
type Client struct{ cli pb.ApiCatalogClient }

// NewClient constructs a Client from an existing gRPC connection.
func NewClient(conn *grpc.ClientConn) *Client { return &Client{cli: pb.NewApiCatalogClient(conn)} }

// authPolicyFromProto maps the catalog proto enum to the gateway AuthPolicy.
// UNSPECIFIED/unknown coerces to PolicyPublic (spec fail-open default).
func authPolicyFromProto(p pb.AuthPolicy) auth_pkg.AuthPolicy {
	switch p {
	case pb.AuthPolicy_BEARER:
		return auth_pkg.PolicyBearer
	case pb.AuthPolicy_ADMIN_KEY:
		return auth_pkg.PolicyAdminKey
	}
	return auth_pkg.PolicyPublic
}

// BuildMapAndAuthSnapshot returns routes + AuthSnapshot in a single ListServices
// pass over ACTIVE services. ListEndpoints is called ONLY for services whose
// HasEndpointOverrides hint is true, bounding fan-out.
func (c *Client) BuildMapAndAuthSnapshot(ctx context.Context) (map[string]string, auth_pkg.AuthSnapshot, error) {
	resp, err := c.cli.ListServices(ctx, &pb.ListServicesRequest{Limit: 1000})
	if err != nil {
		return nil, nil, err
	}
	routes := make(map[string]string, len(resp.GetItems()))
	snap := make(auth_pkg.AuthSnapshot, len(resp.GetItems()))
	for _, s := range resp.GetItems() {
		if s.GetStatus() != pb.Status_ACTIVE {
			continue
		}
		routes["/"+s.GetName()] = s.GetBaseUrl()
		sp := auth_pkg.ServicePolicy{
			Default:     authPolicyFromProto(s.GetAuthPolicy()),
			PublicPaths: map[string]struct{}{},
		}
		for _, p := range s.GetPublicPaths() {
			sp.PublicPaths[p] = struct{}{}
		}
		if s.GetHasEndpointOverrides() {
			epResp, epErr := c.cli.ListEndpoints(ctx, &pb.ListEndpointsRequest{ServiceId: s.GetId()})
			if epErr == nil {
				ea := make(map[string]auth_pkg.AuthPolicy, len(epResp.GetItems()))
				for _, e := range epResp.GetItems() {
					if e.AuthPolicy == nil {
						continue
					}
					ea[e.GetMethod()+" "+e.GetPath()] = authPolicyFromProto(*e.AuthPolicy)
				}
				sp.EndpointAuth = ea
			}
		}
		snap[s.GetName()] = sp
	}
	return routes, snap, nil
}

// BuildMap returns prefix -> base_url for ACTIVE services only.
// Prefix is "/" + service.Name (which already includes the "-service" suffix).
func (c *Client) BuildMap(ctx context.Context) (map[string]string, error) {
	m, _, err := c.BuildMapAndAuthSnapshot(ctx)
	return m, err
}
