package grpcserver

import (
	"encoding/json"
	"reflect"
	"testing"
	"time"

	"api-catalog-service/internal/db"
	pb "api-catalog-service/internal/genproto/api_catalog"
)

func TestServiceRowToProto(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Second)
	okFlag := true
	p, _ := json.Marshal([]string{"rest", "ws"})
	row := db.ServiceRow{
		ID: "id", Name: "n", BaseURL: "u", Protocols: string(p),
		Source: "env", Status: "active",
		LastScannedAt: &now, LastScanOK: &okFlag, CreatedAt: now, UpdatedAt: now,
	}
	pbRow := ServiceRowToProto(row)
	if pbRow.Source != pb.Source_ENV || pbRow.Status != pb.Status_ACTIVE {
		t.Fatalf("enum mapping wrong")
	}
	if len(pbRow.Protocols) != 2 || pbRow.Protocols[0] != pb.Protocol_REST {
		t.Fatalf("protocols wrong: %+v", pbRow.Protocols)
	}
	if !pbRow.LastScanOk {
		t.Fatal("last_scan_ok wrong")
	}
}

func TestEndpointRowToProto(t *testing.T) {
	tags, _ := json.Marshal([]string{"admin", "internal"})
	row := db.EndpointRow{
		ID: "ep1", ServiceID: "svc1", Protocol: "grpc",
		Method: "GET", Path: "/foo", Summary: "summary",
		OperationID: "op1", Tags: string(tags), Deprecated: true,
	}
	ep := EndpointRowToProto(row)
	if ep.Protocol != pb.Protocol_GRPC {
		t.Fatalf("protocol wrong: %v", ep.Protocol)
	}
	if len(ep.Tags) != 2 || ep.Tags[0] != "admin" {
		t.Fatalf("tags wrong: %v", ep.Tags)
	}
	if !ep.Deprecated {
		t.Fatal("deprecated wrong")
	}
}

func TestProtoEnumRoundtrip(t *testing.T) {
	for _, s := range []string{"rest", "ws", "grpc"} {
		if StrFromProto(protoFromStr(s)) != s {
			t.Errorf("roundtrip failed for protocol %q", s)
		}
	}
	for _, s := range []string{"active", "deprecated", "down"} {
		if StatusToStr(statusFromStr(s)) != s {
			t.Errorf("roundtrip failed for status %q", s)
		}
	}
}

func TestServiceRowToProto_AuthPolicy(t *testing.T) {
	row := db.ServiceRow{
		ID: "1", Name: "n", BaseURL: "http://x", Protocols: "[]",
		Source: "manual", Status: "active",
		AuthPolicy:  2, // BEARER
		PublicPaths: `["/health","/ready"]`,
	}
	got := ServiceRowToProto(row)
	if got.GetAuthPolicy() != pb.AuthPolicy_BEARER {
		t.Fatalf("auth_policy=%v; want BEARER", got.GetAuthPolicy())
	}
	if want := []string{"/health", "/ready"}; !reflect.DeepEqual(got.GetPublicPaths(), want) {
		t.Fatalf("public_paths=%v; want %v", got.GetPublicPaths(), want)
	}
}

func TestEndpointRowToProto_AuthPolicy_Override(t *testing.T) {
	policy := 3 // ADMIN_KEY
	row := db.EndpointRow{ID: "e", ServiceID: "s", Protocol: "rest", Path: "/x", AuthPolicy: &policy}
	got := EndpointRowToProto(row)
	if got.GetAuthPolicy() != pb.AuthPolicy_ADMIN_KEY {
		t.Fatalf("auth_policy=%v; want ADMIN_KEY", got.GetAuthPolicy())
	}
}

func TestEndpointRowToProto_AuthPolicy_Unset(t *testing.T) {
	row := db.EndpointRow{ID: "e", ServiceID: "s", Protocol: "rest", Path: "/x", AuthPolicy: nil}
	got := EndpointRowToProto(row)
	if got.AuthPolicy != nil {
		t.Fatalf("expected proto AuthPolicy to remain nil for unset override")
	}
}
