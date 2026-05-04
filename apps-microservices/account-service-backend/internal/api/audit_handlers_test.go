package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/db"
)

type fakeAuditRepo struct {
	rows []db.AuditLog
}

func (f *fakeAuditRepo) List(filters map[string]interface{}, limit, offset int) ([]db.AuditLog, int64, error) {
	out := []db.AuditLog{}
	for _, r := range f.rows {
		ev, ok := filters["event"].(string)
		if ok && r.Event != ev {
			continue
		}
		out = append(out, r)
	}
	return out, int64(len(out)), nil
}

func TestAuditList_FiltersByEvent(t *testing.T) {
	repo := &fakeAuditRepo{rows: []db.AuditLog{
		{Event: "login"}, {Event: "logout"}, {Event: "login"},
	}}
	h := NewAuditHandler(AuditDeps{Repo: repo})
	r := httptest.NewRequest(http.MethodGet, "/api/v1/admin/audit?event=login", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if int(body["total"].(float64)) != 2 {
		t.Fatalf("total=%v", body["total"])
	}
}
