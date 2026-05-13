package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "account-service/internal/genproto/api_catalog"
)

// CatalogClientIface is the set of catalog operations the HTTP handlers need.
// *CatalogClient satisfies this interface.
type CatalogClientIface interface {
	ListServices(ctx context.Context, limit, offset int, filter string) (*pb.ListServicesResponse, error)
	GetService(ctx context.Context, id string) (*pb.Service, error)
	ListEndpoints(ctx context.Context, serviceID string, protocol pb.Protocol) (*pb.ListEndpointsResponse, error)
	Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error)
	Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error)
	Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error)
	RescanAll(ctx context.Context) (*pb.RescanReport, error)
	RescanService(ctx context.Context, id string) (*pb.RescanReport, error)
}

// CatalogAuditFn is called after every mutating operation to record a trail.
// It may be nil — handlers check before calling.
type CatalogAuditFn func(ctx context.Context, actor, action, target string)

// APICatalogDeps bundles the two dependencies the catalog HTTP handler needs.
type APICatalogDeps struct {
	Client CatalogClientIface
	Audit  CatalogAuditFn // may be nil
}

type apiCatalogHandler struct{ d APICatalogDeps }

// NewAPICatalogHandler returns the HTTP handler for all /api/v1/admin/api routes.
func NewAPICatalogHandler(d APICatalogDeps) http.Handler {
	return &apiCatalogHandler{d: d}
}

// ServeHTTP dispatches by method + {id}/{op} path values set by the Go 1.22 mux.
func (h *apiCatalogHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	op := r.PathValue("op")

	switch {
	case id == "" && r.Method == http.MethodGet:
		h.list(w, r)
	case id == "" && r.Method == http.MethodPost:
		h.create(w, r)
	case id == "rescan" && r.Method == http.MethodPost:
		h.rescanAll(w, r)
	case id != "" && op == "rescan" && r.Method == http.MethodPost:
		h.rescanOne(w, r, id)
	case id != "" && op == "" && r.Method == http.MethodGet:
		h.detail(w, r, id)
	case id != "" && op == "" && r.Method == http.MethodPut:
		h.update(w, r, id)
	case id != "" && op == "" && r.Method == http.MethodDelete:
		h.delete(w, r, id)
	default:
		http.Error(w, `{"error":"method_not_allowed"}`, http.StatusMethodNotAllowed)
	}
}

func (h *apiCatalogHandler) list(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 100
	}
	offset, _ := strconv.Atoi(r.URL.Query().Get("offset"))
	filter := r.URL.Query().Get("filter")

	resp, err := h.d.Client.ListServices(r.Context(), limit, offset, filter)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": servicesToJSON(resp.GetItems()),
		"total": resp.GetTotal(),
	})
}

func (h *apiCatalogHandler) detail(w http.ResponseWriter, r *http.Request, id string) {
	svc, err := h.d.Client.GetService(r.Context(), id)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	eps, err := h.d.Client.ListEndpoints(r.Context(), id, pb.Protocol_PROTOCOL_UNSPECIFIED)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"service":   serviceToJSON(svc),
		"endpoints": endpointsToJSON(eps.GetItems()),
	})
}

type createReq struct {
	Name        string   `json:"name"`
	BaseUrl     string   `json:"baseUrl"`
	Protocols   []string `json:"protocols"`
	Description string   `json:"description"`
	Owner       string   `json:"owner"`
	Tags        []string `json:"tags"`
	ApiInfoUrl  string   `json:"apiInfoUrl"`
	GrpcAddress string   `json:"grpcAddress"`
}

func (h *apiCatalogHandler) create(w http.ResponseWriter, r *http.Request) {
	var body createReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, `{"error":"invalid_json"}`, http.StatusBadRequest)
		return
	}
	actor := actorEmail(r)
	req := &pb.CreateServiceRequest{
		Name:        body.Name,
		BaseUrl:     body.BaseUrl,
		Protocols:   protocolsFromStrings(body.Protocols),
		Description: body.Description,
		Owner:       body.Owner,
		Tags:        body.Tags,
		ApiInfoUrl:  body.ApiInfoUrl,
		GrpcAddress: body.GrpcAddress,
		CreatedBy:   actor,
	}
	svc, err := h.d.Client.Create(r.Context(), req)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	h.audit(r.Context(), actor, "catalog.create", svc.GetId())
	writeJSON(w, http.StatusCreated, serviceToJSON(svc))
}

type updateReq struct {
	Description *string  `json:"description,omitempty"`
	Owner       *string  `json:"owner,omitempty"`
	Tags        []string `json:"tags"`
	Status      *string  `json:"status,omitempty"`
}

func (h *apiCatalogHandler) update(w http.ResponseWriter, r *http.Request, id string) {
	var body updateReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, `{"error":"invalid_json"}`, http.StatusBadRequest)
		return
	}
	req := &pb.UpdateServiceRequest{
		Id:          id,
		Description: body.Description,
		Owner:       body.Owner,
		Tags:        body.Tags,
	}
	if body.Status != nil {
		st := statusFromString(*body.Status)
		req.Status = &st
	}
	svc, err := h.d.Client.Update(r.Context(), req)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	h.audit(r.Context(), actorEmail(r), "catalog.update", id)
	writeJSON(w, http.StatusOK, serviceToJSON(svc))
}

func (h *apiCatalogHandler) delete(w http.ResponseWriter, r *http.Request, id string) {
	if _, err := h.d.Client.Delete(r.Context(), id); err != nil {
		writeGRPCError(w, err)
		return
	}
	h.audit(r.Context(), actorEmail(r), "catalog.delete", id)
	writeJSON(w, http.StatusOK, map[string]any{"deleted": true})
}

func (h *apiCatalogHandler) rescanAll(w http.ResponseWriter, r *http.Request) {
	rep, err := h.d.Client.RescanAll(r.Context())
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	h.audit(r.Context(), actorEmail(r), "catalog.rescan_all", "")
	writeJSON(w, http.StatusOK, reportToJSON(rep))
}

func (h *apiCatalogHandler) rescanOne(w http.ResponseWriter, r *http.Request, id string) {
	rep, err := h.d.Client.RescanService(r.Context(), id)
	if err != nil {
		writeGRPCError(w, err)
		return
	}
	h.audit(r.Context(), actorEmail(r), "catalog.rescan_service", id)
	writeJSON(w, http.StatusOK, reportToJSON(rep))
}

func (h *apiCatalogHandler) audit(ctx context.Context, actor, action, target string) {
	if h.d.Audit != nil {
		h.d.Audit(ctx, actor, action, target)
	}
}

// --- JSON helpers ---

func writeJSON(w http.ResponseWriter, code int, body any) {
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(body)
}

func writeGRPCError(w http.ResponseWriter, err error) {
	code := status.Code(err)
	var httpStatus int
	switch code {
	case codes.NotFound:
		httpStatus = http.StatusNotFound
	case codes.AlreadyExists:
		httpStatus = http.StatusConflict
	case codes.InvalidArgument:
		httpStatus = http.StatusBadRequest
	case codes.Unauthenticated:
		httpStatus = http.StatusUnauthorized
	case codes.Unavailable:
		httpStatus = http.StatusServiceUnavailable
	default:
		httpStatus = http.StatusInternalServerError
	}
	msg := status.Convert(err).Message()
	writeJSON(w, httpStatus, map[string]string{"error": msg})
}

// actorEmail extracts the authenticated user's email from the request context.
// The auth middleware stores it under the "user_email" key.
func actorEmail(r *http.Request) string {
	type ctxKey string
	if v := r.Context().Value(ctxKey("user_email")); v != nil {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

// --- Protocol / Status / Source conversion helpers ---

func protocolsFromStrings(s []string) []pb.Protocol {
	out := make([]pb.Protocol, 0, len(s))
	for _, p := range s {
		switch strings.ToLower(p) {
		case "rest":
			out = append(out, pb.Protocol_REST)
		case "ws":
			out = append(out, pb.Protocol_WS)
		case "grpc":
			out = append(out, pb.Protocol_GRPC)
		}
	}
	return out
}

func protocolStrings(p []pb.Protocol) []string {
	out := make([]string, 0, len(p))
	for _, x := range p {
		switch x {
		case pb.Protocol_REST:
			out = append(out, "rest")
		case pb.Protocol_WS:
			out = append(out, "ws")
		case pb.Protocol_GRPC:
			out = append(out, "grpc")
		}
	}
	return out
}

func statusFromString(s string) pb.Status {
	switch strings.ToLower(s) {
	case "active":
		return pb.Status_ACTIVE
	case "deprecated":
		return pb.Status_DEPRECATED
	case "down":
		return pb.Status_DOWN
	}
	return pb.Status_STATUS_UNSPECIFIED
}

func statusToString(s pb.Status) string {
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

func sourceToString(s pb.Source) string {
	switch s {
	case pb.Source_ENV:
		return "env"
	case pb.Source_MANUAL:
		return "manual"
	case pb.Source_SCAN:
		return "scan"
	}
	return ""
}

// --- Proto → map serialisers ---

func serviceToJSON(s *pb.Service) map[string]any {
	out := map[string]any{
		"id":            s.GetId(),
		"name":          s.GetName(),
		"baseUrl":       s.GetBaseUrl(),
		"protocols":     protocolStrings(s.GetProtocols()),
		"source":        sourceToString(s.GetSource()),
		"status":        statusToString(s.GetStatus()),
		"description":   s.GetDescription(),
		"owner":         s.GetOwner(),
		"tags":          s.GetTags(),
		"apiInfoUrl":    s.GetApiInfoUrl(),
		"grpcAddress":   s.GetGrpcAddress(),
		"lastScanOk":    s.GetLastScanOk(),
		"lastScanError": s.GetLastScanError(),
	}
	if ts := s.GetLastScannedAt(); ts != nil {
		out["lastScannedAt"] = ts.AsTime()
	}
	if ts := s.GetCreatedAt(); ts != nil {
		out["createdAt"] = ts.AsTime()
	}
	if ts := s.GetUpdatedAt(); ts != nil {
		out["updatedAt"] = ts.AsTime()
	}
	return out
}

func servicesToJSON(items []*pb.Service) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, s := range items {
		out = append(out, serviceToJSON(s))
	}
	return out
}

func endpointToJSON(e *pb.Endpoint) map[string]any {
	return map[string]any{
		"id":          e.GetId(),
		"serviceId":   e.GetServiceId(),
		"protocol":    strings.ToLower(e.GetProtocol().String()),
		"method":      e.GetMethod(),
		"path":        e.GetPath(),
		"summary":     e.GetSummary(),
		"operationId": e.GetOperationId(),
		"tags":        e.GetTags(),
		"deprecated":  e.GetDeprecated(),
	}
}

func endpointsToJSON(items []*pb.Endpoint) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, e := range items {
		out = append(out, endpointToJSON(e))
	}
	return out
}

func reportToJSON(r *pb.RescanReport) map[string]any {
	out := map[string]any{
		"servicesScanned": r.GetServicesScanned(),
		"servicesOk":      r.GetServicesOk(),
		"servicesFailed":  r.GetServicesFailed(),
		"errors":          r.GetErrors(),
	}
	if ts := r.GetFinishedAt(); ts != nil {
		out["finishedAt"] = ts.AsTime()
	}
	return out
}
