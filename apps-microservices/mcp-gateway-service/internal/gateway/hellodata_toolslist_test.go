package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

// Un backend injoignable ne doit PAS rendre les outils visibles. C'est la
// divergence deliberee d'avec fetchZohoTools, qui se replie sur le cache.
func TestFetchHellodataTools_BackendInjoignableRendListeVide(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer s.Close()

	sg := &ScopedGateway{gatewayUsers: fakeUsers{"alice@example.test": "admin"}}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix, MessageURL: s.URL}

	if got := sg.fetchHellodataTools(context.Background(), b); len(got) != 0 {
		t.Errorf("%d outils, attendu 0 sur backend injoignable", len(got))
	}
}

// Un backend qui repond une liste vide — appelant non autorise — rend
// bien zero outil, sans repli sur le cache.
func TestFetchHellodataTools_ListeVideRespectee(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}`))
	}))
	defer s.Close()

	sg := &ScopedGateway{gatewayUsers: fakeUsers{"dave@example.test": "readonly"}}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix, MessageURL: s.URL}

	if got := sg.fetchHellodataTools(context.Background(), b); len(got) != 0 {
		t.Errorf("%d outils, attendu 0 pour un appelant non autorise", len(got))
	}
}
