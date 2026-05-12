package grpcserver

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	"api-catalog-service/internal/db"
	pb "api-catalog-service/internal/genproto/api_catalog"
	"api-catalog-service/internal/repository"
	"api-catalog-service/internal/scanner"
)

// Deps holds the dependencies injected into the gRPC server.
type Deps struct {
	Services  *repository.ServiceRepo
	Endpoints *repository.EndpointRepo
	Scanner   *scanner.Scanner
	Seeds     func() map[string]string
	AdminKey  string
}

// Server implements the ApiCatalog gRPC service.
type Server struct {
	pb.UnimplementedApiCatalogServer
	d Deps
}

// NewServer creates a new Server with the given dependencies.
func NewServer(d Deps) *Server { return &Server{d: d} }

func (s *Server) ListServices(ctx context.Context, req *pb.ListServicesRequest) (*pb.ListServicesResponse, error) {
	items, total, err := s.d.Services.List(int(req.GetLimit()), int(req.GetOffset()), req.GetFilter())
	if err != nil {
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	out := &pb.ListServicesResponse{Total: total}
	for _, r := range items {
		out.Items = append(out.Items, ServiceRowToProto(r))
	}
	return out, nil
}

func (s *Server) GetService(ctx context.Context, req *pb.GetServiceRequest) (*pb.Service, error) {
	row, err := s.d.Services.GetByID(req.GetId())
	if errors.Is(err, repository.ErrNotFound) {
		return nil, status.Error(codes.NotFound, "service not found")
	}
	if err != nil {
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	return ServiceRowToProto(*row), nil
}

func (s *Server) ListEndpoints(ctx context.Context, req *pb.ListEndpointsRequest) (*pb.ListEndpointsResponse, error) {
	items, err := s.d.Endpoints.ListForService(req.GetServiceId(), StrFromProto(req.GetProtocol()))
	if err != nil {
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	out := &pb.ListEndpointsResponse{}
	for _, r := range items {
		out.Items = append(out.Items, EndpointRowToProto(r))
	}
	return out, nil
}

func (s *Server) CreateService(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) {
	if req.GetName() == "" || req.GetBaseUrl() == "" {
		return nil, status.Error(codes.InvalidArgument, "name and base_url required")
	}
	protos := make([]string, 0, len(req.GetProtocols()))
	for _, p := range req.GetProtocols() {
		if v := StrFromProto(p); v != "" {
			protos = append(protos, v)
		}
	}
	pj, _ := json.Marshal(protos)
	var tagsJSON string
	if len(req.GetTags()) > 0 {
		b, _ := json.Marshal(req.GetTags())
		tagsJSON = string(b)
	}
	row := &db.ServiceRow{
		ID: uuid.NewString(), Name: req.GetName(), BaseURL: req.GetBaseUrl(),
		Protocols: string(pj), Source: "manual", Status: "active",
		Description: req.GetDescription(), Owner: req.GetOwner(),
		Tags: tagsJSON, APIInfoURL: req.GetApiInfoUrl(), GRPCAddress: req.GetGrpcAddress(),
		CreatedBy: req.GetCreatedBy(),
	}
	if err := s.d.Services.Create(row); err != nil {
		return nil, status.Error(codes.AlreadyExists, err.Error())
	}
	got, _ := s.d.Services.GetByID(row.ID)
	return ServiceRowToProto(*got), nil
}

func (s *Server) UpdateService(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) {
	fields := map[string]any{}
	if req.Description != nil {
		fields["description"] = req.GetDescription()
	}
	if req.Owner != nil {
		fields["owner"] = req.GetOwner()
	}
	if len(req.GetTags()) > 0 {
		b, _ := json.Marshal(req.GetTags())
		fields["tags"] = string(b)
	}
	if req.Status != nil {
		fields["status"] = StatusToStr(req.GetStatus())
	}
	if len(fields) == 0 {
		return nil, status.Error(codes.InvalidArgument, "no fields to update")
	}
	if err := s.d.Services.Update(req.GetId(), fields); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			return nil, status.Error(codes.NotFound, "service not found")
		}
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	got, _ := s.d.Services.GetByID(req.GetId())
	return ServiceRowToProto(*got), nil
}

func (s *Server) DeleteService(ctx context.Context, req *pb.DeleteServiceRequest) (*pb.DeleteServiceResponse, error) {
	if err := s.d.Services.Delete(req.GetId()); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			return nil, status.Error(codes.NotFound, "service not found")
		}
		return nil, status.Error(codes.Unavailable, err.Error())
	}
	return &pb.DeleteServiceResponse{Deleted: true}, nil
}

func (s *Server) RescanAll(ctx context.Context, req *pb.RescanAllRequest) (*pb.RescanReport, error) {
	if s.d.Scanner == nil {
		return nil, status.Error(codes.Unavailable, "scanner not configured")
	}
	rep := s.d.Scanner.Run(ctx, s.d.Seeds())
	return &pb.RescanReport{
		ServicesScanned: int32(rep.ServicesScanned),
		ServicesOk:      int32(rep.ServicesOK),
		ServicesFailed:  int32(rep.ServicesFailed),
		Errors:          rep.Errors,
		FinishedAt:      timestamppb.New(rep.FinishedAt),
	}, nil
}

func (s *Server) RescanService(ctx context.Context, req *pb.RescanServiceRequest) (*pb.RescanReport, error) {
	if s.d.Scanner == nil {
		return nil, status.Error(codes.Unavailable, "scanner not configured")
	}
	row, err := s.d.Services.GetByID(req.GetId())
	if err != nil {
		return nil, status.Error(codes.NotFound, "service not found")
	}
	seeds := map[string]string{row.Name: row.BaseURL}
	rep := s.d.Scanner.Run(ctx, seeds)
	return &pb.RescanReport{
		ServicesScanned: int32(rep.ServicesScanned),
		ServicesOk:      int32(rep.ServicesOK),
		ServicesFailed:  int32(rep.ServicesFailed),
		Errors:          rep.Errors,
		FinishedAt:      timestamppb.New(rep.FinishedAt),
	}, nil
}
