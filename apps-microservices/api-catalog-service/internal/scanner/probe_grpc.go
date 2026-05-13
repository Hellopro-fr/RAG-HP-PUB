package scanner

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/jhump/protoreflect/grpcreflect"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"api-catalog-service/internal/db"
)

func ProbeGRPC(ctx context.Context, address string, timeout time.Duration, opts ...grpc.DialOption) ([]db.EndpointRow, error) {
	if len(opts) == 0 {
		opts = []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
	}
	// grpc.NewClient dials lazily; the first RPC (ListServices) establishes the connection.
	conn, err := grpc.NewClient(address, opts...)
	if err != nil {
		return nil, nil
	}
	defer conn.Close()

	rctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cli := grpcreflect.NewClientAuto(rctx, conn)
	defer cli.Reset()

	services, err := cli.ListServices()
	if err != nil {
		return nil, nil
	}

	var out []db.EndpointRow
	for _, svc := range services {
		sd, err := cli.ResolveService(svc)
		if err != nil {
			continue
		}
		for _, m := range sd.GetMethods() {
			out = append(out, db.EndpointRow{
				ID:       uuid.NewString(),
				Protocol: "grpc",
				Path:     svc + "/" + m.GetName(),
				Summary:  "",
			})
		}
	}
	return out, nil
}
