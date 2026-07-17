package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "account-service/internal/genproto/api_catalog"
)

type mockCatalog struct {
	listResp     *pb.ListServicesResponse
	listErr      error
	createReq    *pb.CreateServiceRequest
	createResp   *pb.Service
	deleteCalled string
	rescanCalled bool
}

func (m *mockCatalog) ListServices(ctx context.Context, limit, offset int, filter string) (*pb.ListServicesResponse, error) {
	return m.listResp, m.listErr
}
func (m *mockCatalog) GetService(ctx context.Context, id string) (*pb.Service, error) {
	return nil, status.Error(codes.NotFound, "n/a")
}
func (m *mockCatalog) ListEndpoints(ctx context.Context, sid string, p pb.Protocol) (*pb.ListEndpointsResponse, error) {
	return &pb.ListEndpointsResponse{}, nil
}
func (m *mockCatalog) Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) {
	m.createReq = req
	return m.createResp, nil
}
func (m *mockCatalog) Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) {
	return &pb.Service{Id: req.GetId()}, nil
}
func (m *mockCatalog) Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error) {
	m.deleteCalled = id
	return &pb.DeleteServiceResponse{Deleted: true}, nil
}
func (m *mockCatalog) RescanAll(ctx context.Context) (*pb.RescanReport, error) {
	m.rescanCalled = true
	return &pb.RescanReport{ServicesScanned: 1}, nil
}
func (m *mockCatalog) RescanService(ctx context.Context, id string) (*pb.RescanReport, error) {
	return &pb.RescanReport{ServicesScanned: 1}, nil
}

func TestAPICatalog_List(t *testing.T) {
	mc := &mockCatalog{listResp: &pb.ListServicesResponse{
		Total: 1, Items: []*pb.Service{{Id: "a", Name: "foo-service"}},
	}}
	h := NewAPICatalogHandler(APICatalogDeps{Client: mc})

	rr := httptest.NewRecorder()
	req := httptest.NewRequest("GET", "/api/v1/admin/api?limit=10", nil)
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d", rr.Code)
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["total"].(float64) != 1 {
		t.Fatalf("total = %v", body["total"])
	}
}

func TestAPICatalog_Create(t *testing.T) {
	mc := &mockCatalog{createResp: &pb.Service{Id: "x"}}
	h := NewAPICatalogHandler(APICatalogDeps{Client: mc})

	body, _ := json.Marshal(map[string]any{
		"name": "x-service", "baseUrl": "http://x", "protocols": []string{"rest"},
	})
	req := httptest.NewRequest("POST", "/api/v1/admin/api", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusCreated {
		t.Fatalf("status = %d body = %s", rr.Code, rr.Body.String())
	}
	if mc.createReq.GetName() != "x-service" {
		t.Fatalf("create req name = %q", mc.createReq.GetName())
	}
}

func TestAPICatalog_NotFound_Translates(t *testing.T) {
	mc := &mockCatalog{}
	h := NewAPICatalogHandler(APICatalogDeps{Client: mc})

	req := httptest.NewRequest("GET", "/api/v1/admin/api/missing", nil)
	req.SetPathValue("id", "missing")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected 404 got %d", rr.Code)
	}
}

func TestAPICatalog_RescanAll(t *testing.T) {
	mc := &mockCatalog{}
	h := NewAPICatalogHandler(APICatalogDeps{Client: mc})

	req := httptest.NewRequest("POST", "/api/v1/admin/api/rescan", nil)
	req.SetPathValue("id", "rescan")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d", rr.Code)
	}
	if !mc.rescanCalled {
		t.Fatal("rescan not called")
	}
}
