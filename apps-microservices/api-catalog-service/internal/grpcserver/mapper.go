package grpcserver

import (
	"encoding/json"

	"google.golang.org/protobuf/types/known/timestamppb"

	"api-catalog-service/internal/db"
	pb "api-catalog-service/internal/genproto/api_catalog"
)

func ServiceRowToProto(r db.ServiceRow) *pb.Service {
	var protos []string
	_ = json.Unmarshal([]byte(r.Protocols), &protos)
	var tags []string
	if r.Tags != "" {
		_ = json.Unmarshal([]byte(r.Tags), &tags)
	}
	pbProtos := make([]pb.Protocol, 0, len(protos))
	for _, s := range protos {
		pbProtos = append(pbProtos, protoFromStr(s))
	}
	out := &pb.Service{
		Id: r.ID, Name: r.Name, BaseUrl: r.BaseURL,
		Protocols:     pbProtos,
		Source:        sourceFromStr(r.Source),
		Status:        statusFromStr(r.Status),
		Description:   r.Description,
		Owner:         r.Owner,
		Tags:          tags,
		ApiInfoUrl:    r.APIInfoURL,
		GrpcAddress:   r.GRPCAddress,
		LastScanError: r.LastScanError,
		CreatedAt:     timestamppb.New(r.CreatedAt),
		UpdatedAt:     timestamppb.New(r.UpdatedAt),
	}
	if r.LastScannedAt != nil {
		out.LastScannedAt = timestamppb.New(*r.LastScannedAt)
	}
	if r.LastScanOK != nil {
		out.LastScanOk = *r.LastScanOK
	}
	return out
}

func EndpointRowToProto(r db.EndpointRow) *pb.Endpoint {
	var tags []string
	if r.Tags != "" {
		_ = json.Unmarshal([]byte(r.Tags), &tags)
	}
	return &pb.Endpoint{
		Id: r.ID, ServiceId: r.ServiceID, Method: r.Method, Path: r.Path,
		Summary: r.Summary, OperationId: r.OperationID, Tags: tags,
		Deprecated: r.Deprecated, Protocol: protoFromStr(r.Protocol),
	}
}

func protoFromStr(s string) pb.Protocol {
	switch s {
	case "rest":
		return pb.Protocol_REST
	case "ws":
		return pb.Protocol_WS
	case "grpc":
		return pb.Protocol_GRPC
	}
	return pb.Protocol_PROTOCOL_UNSPECIFIED
}

// StrFromProto converts a Protocol enum to its string representation for DB storage.
func StrFromProto(p pb.Protocol) string {
	switch p {
	case pb.Protocol_REST:
		return "rest"
	case pb.Protocol_WS:
		return "ws"
	case pb.Protocol_GRPC:
		return "grpc"
	}
	return ""
}

func sourceFromStr(s string) pb.Source {
	switch s {
	case "env":
		return pb.Source_ENV
	case "manual":
		return pb.Source_MANUAL
	case "scan":
		return pb.Source_SCAN
	}
	return pb.Source_SOURCE_UNSPECIFIED
}

func statusFromStr(s string) pb.Status {
	switch s {
	case "active":
		return pb.Status_ACTIVE
	case "deprecated":
		return pb.Status_DEPRECATED
	case "down":
		return pb.Status_DOWN
	}
	return pb.Status_STATUS_UNSPECIFIED
}

// StatusToStr converts a Status enum to its string representation for DB storage.
func StatusToStr(s pb.Status) string {
	switch s {
	case pb.Status_ACTIVE:
		return "active"
	case pb.Status_DEPRECATED:
		return "deprecated"
	case pb.Status_DOWN:
		return "down"
	}
	return ""
}
