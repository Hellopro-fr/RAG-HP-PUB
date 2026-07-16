package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
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
func (m *mockCatalog) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) {
	return &pb.Endpoint{Id: req.GetId()}, nil
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

// --- fakeCatalog: full-featured test double for new tests ---

type fakeCatalog struct {
	lastCreate         *pb.CreateServiceRequest
	lastUpdate         *pb.UpdateServiceRequest
	lastUpdateEndpoint *pb.UpdateEndpointRequest
}

func (f *fakeCatalog) ListServices(ctx context.Context, l, o int, fil string) (*pb.ListServicesResponse, error) {
	return &pb.ListServicesResponse{}, nil
}
func (f *fakeCatalog) GetService(ctx context.Context, id string) (*pb.Service, error) {
	return &pb.Service{Id: id}, nil
}
func (f *fakeCatalog) ListEndpoints(ctx context.Context, id string, p pb.Protocol) (*pb.ListEndpointsResponse, error) {
	return &pb.ListEndpointsResponse{}, nil
}
func (f *fakeCatalog) Create(ctx context.Context, req *pb.CreateServiceRequest) (*pb.Service, error) {
	f.lastCreate = req
	return &pb.Service{Id: "new"}, nil
}
func (f *fakeCatalog) Update(ctx context.Context, req *pb.UpdateServiceRequest) (*pb.Service, error) {
	f.lastUpdate = req
	return &pb.Service{Id: req.GetId()}, nil
}
func (f *fakeCatalog) Delete(ctx context.Context, id string) (*pb.DeleteServiceResponse, error) {
	return &pb.DeleteServiceResponse{Deleted: true}, nil
}
func (f *fakeCatalog) UpdateEndpoint(ctx context.Context, req *pb.UpdateEndpointRequest) (*pb.Endpoint, error) {
	f.lastUpdateEndpoint = req
	return &pb.Endpoint{Id: req.GetId()}, nil
}
func (f *fakeCatalog) RescanAll(ctx context.Context) (*pb.RescanReport, error) {
	return &pb.RescanReport{}, nil
}
func (f *fakeCatalog) RescanService(ctx context.Context, id string) (*pb.RescanReport, error) {
	return &pb.RescanReport{}, nil
}

func newHandler(t *testing.T, c CatalogClientIface) http.Handler {
	t.Helper()
	return NewAPICatalogHandler(APICatalogDeps{Client: c})
}

// --- New tests ---

func TestCreate_RejectsInvalidAuthPolicy(t *testing.T) {
	h := newHandler(t, &fakeCatalog{})
	body := strings.NewReader(`{"name":"x","baseUrl":"http://x","authPolicy":"banana"}`)
	req := httptest.NewRequest("POST", "/api/v1/admin/api", body)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("status=%d; want 400", w.Code)
	}
	if !strings.Contains(w.Body.String(), "invalid_auth_policy") {
		t.Fatalf("body=%q; want invalid_auth_policy", w.Body.String())
	}
}

func TestCreate_RejectsInvalidPublicPath(t *testing.T) {
	cases := []string{`["no-slash"]`, `["/with/*"]`, `["/with?q"]`, `[""]`}
	for _, jsonArr := range cases {
		h := newHandler(t, &fakeCatalog{})
		body := strings.NewReader(`{"name":"x","baseUrl":"http://x","publicPaths":` + jsonArr + `}`)
		req := httptest.NewRequest("POST", "/api/v1/admin/api", body)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		if w.Code != http.StatusBadRequest {
			t.Fatalf("paths=%s status=%d; want 400", jsonArr, w.Code)
		}
	}
}

func TestCreate_NormalizesPublicPath_StripTrailingSlash(t *testing.T) {
	fake := &fakeCatalog{}
	h := newHandler(t, fake)
	body := strings.NewReader(`{"name":"x","baseUrl":"http://x","authPolicy":"bearer","publicPaths":["/foo/"]}`)
	req := httptest.NewRequest("POST", "/api/v1/admin/api", body)
	h.ServeHTTP(httptest.NewRecorder(), req)
	if got := fake.lastCreate.GetPublicPaths(); !reflect.DeepEqual(got, []string{"/foo"}) {
		t.Fatalf("paths=%v; want [/foo]", got)
	}
	if fake.lastCreate.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("policy=%v; want BEARER", fake.lastCreate.GetAuthPolicy())
	}
}

func TestUpdateEndpoint_RoundTrip(t *testing.T) {
	fake := &fakeCatalog{}
	h := newHandler(t, fake)
	body := strings.NewReader(`{"authPolicy":"bearer"}`)
	req := httptest.NewRequest("PUT", "/api/v1/admin/api/svc-1/endpoints/ep-1", body)
	req.SetPathValue("id", "svc-1")
	req.SetPathValue("endpoint_id", "ep-1")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s; want 200", w.Code, w.Body.String())
	}
	if fake.lastUpdateEndpoint.GetId() != "ep-1" || fake.lastUpdateEndpoint.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("got=%+v; want id=ep-1 BEARER", fake.lastUpdateEndpoint)
	}
}

func TestUpdateEndpoint_ClearWithNull(t *testing.T) {
	fake := &fakeCatalog{}
	h := newHandler(t, fake)
	body := strings.NewReader(`{"authPolicy":null}`)
	req := httptest.NewRequest("PUT", "/api/v1/admin/api/svc-1/endpoints/ep-1", body)
	req.SetPathValue("id", "svc-1")
	req.SetPathValue("endpoint_id", "ep-1")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d; want 200", w.Code)
	}
	if fake.lastUpdateEndpoint.AuthPolicy != nil {
		t.Fatalf("expected nil AuthPolicy on clear")
	}
}
