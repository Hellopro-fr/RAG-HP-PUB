package logout

import (
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestDeliver_Success(t *testing.T) {
	var received int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Logout-Signature") == "" {
			t.Error("missing signature header")
		}
		atomic.AddInt32(&received, 1)
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	d := NewDeliverer(DelivererConfig{Timeout: 2 * time.Second, MaxAttempts: 3})
	res := d.Deliver(srv.URL, "secret", []byte(`{"sub":"a@x"}`))
	if !res.Sent {
		t.Fatalf("Sent=false attempts=%d err=%s", res.Attempts, res.LastError)
	}
	if got := atomic.LoadInt32(&received); got != 1 {
		t.Errorf("received=%d", got)
	}
}

func TestDeliver_RetriesOn5xx(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt32(&hits, 1)
		if n < 3 {
			http.Error(w, "boom", http.StatusBadGateway)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	d := NewDeliverer(DelivererConfig{Timeout: 2 * time.Second, MaxAttempts: 3, BackoffBase: 1 * time.Millisecond})
	res := d.Deliver(srv.URL, "secret", []byte(`{}`))
	if !res.Sent {
		t.Fatalf("Sent=false attempts=%d", res.Attempts)
	}
	if res.Attempts != 3 {
		t.Errorf("Attempts=%d want 3", res.Attempts)
	}
}

func TestDeliver_GivesUpAfterMax(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()
	d := NewDeliverer(DelivererConfig{Timeout: 2 * time.Second, MaxAttempts: 2, BackoffBase: 1 * time.Millisecond})
	res := d.Deliver(srv.URL, "secret", []byte(`{}`))
	if res.Sent {
		t.Fatal("expected Sent=false")
	}
	if res.Attempts != 2 {
		t.Errorf("Attempts=%d", res.Attempts)
	}
}
