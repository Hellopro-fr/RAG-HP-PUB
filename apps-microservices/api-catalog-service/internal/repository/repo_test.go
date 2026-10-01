package repository

import (
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"api-catalog-service/internal/db"
)

func newDB(t *testing.T) *gorm.DB {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(g); err != nil {
		t.Fatal(err)
	}
	return g
}

func TestServiceRepo_CreateGet(t *testing.T) {
	r := NewServiceRepo(newDB(t))
	row := &db.ServiceRow{
		ID: "00000000-0000-0000-0000-000000000001", Name: "foo-service",
		BaseURL: "http://foo:8000", Protocols: `["rest"]`, Source: "env", Status: "active",
	}
	if err := r.Create(row); err != nil {
		t.Fatal(err)
	}
	got, err := r.GetByID(row.ID)
	if err != nil || got.Name != "foo-service" {
		t.Fatalf("GetByID got=%v err=%v", got, err)
	}
}

func TestServiceRepo_List_OrdersByName(t *testing.T) {
	r := NewServiceRepo(newDB(t))
	_ = r.Create(&db.ServiceRow{ID: "1", Name: "b-service", BaseURL: "x", Protocols: "[]", Source: "env", Status: "active"})
	_ = r.Create(&db.ServiceRow{ID: "2", Name: "a-service", BaseURL: "x", Protocols: "[]", Source: "env", Status: "active"})
	items, total, err := r.List(10, 0, "")
	if err != nil || total != 2 || items[0].Name != "a-service" {
		t.Fatalf("List items=%v total=%d err=%v", items, total, err)
	}
}

func TestEndpointRepo_BulkReplace(t *testing.T) {
	g := newDB(t)
	sr := NewServiceRepo(g)
	er := NewEndpointRepo(g)
	_ = sr.Create(&db.ServiceRow{ID: "s1", Name: "x-service", BaseURL: "x", Protocols: "[]", Source: "env", Status: "active"})
	if err := er.ReplaceForService("s1", []db.EndpointRow{
		{ID: "e1", ServiceID: "s1", Protocol: "rest", Method: "GET", Path: "/a"},
	}); err != nil {
		t.Fatal(err)
	}
	if err := er.ReplaceForService("s1", []db.EndpointRow{
		{ID: "e2", ServiceID: "s1", Protocol: "rest", Method: "POST", Path: "/b"},
	}); err != nil {
		t.Fatal(err)
	}
	got, _ := er.ListForService("s1", "")
	if len(got) != 1 || got[0].Path != "/b" {
		t.Fatalf("after replace, want [/b], got %+v", got)
	}
}
