package httpapi

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWriteJSON(t *testing.T) {
	w := httptest.NewRecorder()
	WriteJSON(w, 201, map[string]int{"x": 1})
	if w.Code != 201 {
		t.Errorf("status = %d, want 201", w.Code)
	}
	if ct := w.Header().Get("Content-Type"); ct != "application/json; charset=utf-8" {
		t.Errorf("Content-Type = %q", ct)
	}
	var got map[string]int
	if err := json.Unmarshal(w.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got["x"] != 1 {
		t.Errorf("body = %v", got)
	}
}

func TestWriteError(t *testing.T) {
	w := httptest.NewRecorder()
	WriteError(w, 401, "Invalid password")
	if w.Code != 401 {
		t.Errorf("status = %d, want 401", w.Code)
	}
	body := strings.TrimSpace(w.Body.String())
	if body != `{"error":"Invalid password"}` {
		t.Errorf("body = %q", body)
	}
}

func TestDecodeJSON_OK(t *testing.T) {
	r := httptest.NewRequest("POST", "/", bytes.NewBufferString(`{"x":42}`))
	var dst struct {
		X int `json:"x"`
	}
	if err := DecodeJSON(r, &dst); err != nil {
		t.Fatal(err)
	}
	if dst.X != 42 {
		t.Errorf("x = %d", dst.X)
	}
}

func TestDecodeJSON_Invalid(t *testing.T) {
	r := httptest.NewRequest("POST", "/", bytes.NewBufferString(`{not json`))
	var dst map[string]any
	if err := DecodeJSON(r, &dst); err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestErrorSentinels(t *testing.T) {
	cases := []struct {
		err    *HTTPError
		status int
	}{
		{ErrNotFound, 404}, {ErrUnauthorized, 401},
		{ErrForbidden, 403}, {ErrBadRequest, 400},
		{ErrConflict, 409}, {ErrPayloadTooBig, 413},
	}
	for _, c := range cases {
		if c.err.Status != c.status {
			t.Errorf("%s: status = %d, want %d", c.err.Msg, c.err.Status, c.status)
		}
		if c.err.Error() != c.err.Msg {
			t.Errorf("Error() = %q, want %q", c.err.Error(), c.err.Msg)
		}
	}
}
