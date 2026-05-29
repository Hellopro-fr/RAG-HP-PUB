package proxy

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestForwardJSONRPC_PassesBodyAndHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if got := string(body); got != `{"jsonrpc":"2.0","method":"tools/list","id":1}` {
			t.Fatalf("upstream body = %q", got)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer alice" {
			t.Fatalf("upstream Authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","result":{"tools":[]},"id":1}`))
	}))
	defer upstream.Close()

	body := bytes.NewBufferString(`{"jsonrpc":"2.0","method":"tools/list","id":1}`)
	hdrs := map[string]string{"Authorization": "Bearer alice"}

	resp, err := ForwardJSONRPC(context.Background(), upstream.URL, hdrs, body, 5*time.Second)
	if err != nil {
		t.Fatalf("ForwardJSONRPC: %v", err)
	}
	defer resp.Close()

	got, _ := io.ReadAll(resp)
	if string(got) != `{"jsonrpc":"2.0","result":{"tools":[]},"id":1}` {
		t.Fatalf("response body = %q", got)
	}
}
