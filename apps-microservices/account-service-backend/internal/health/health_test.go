package health

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

type fakePinger struct {
	ok bool
}

func (f fakePinger) Ping() error {
	if !f.ok {
		return errors.New("down")
	}
	return nil
}

func TestHealth_OK(t *testing.T) {
	h := NewHandler("v1", fakePinger{ok: true})
	r := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "ok" {
		t.Errorf("status=%v", body["status"])
	}
	if body["db"] != "ok" {
		t.Errorf("db=%v", body["db"])
	}
}

func TestHealth_DBDown(t *testing.T) {
	h := NewHandler("v1", fakePinger{ok: false})
	r := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("Code=%d", w.Code)
	}
}
