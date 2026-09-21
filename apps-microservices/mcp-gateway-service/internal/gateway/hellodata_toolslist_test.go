package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/scopetoken"
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

// Le cas positif, celui qui manquait : un appelant autorise voit les trois
// outils, prefixes. Ils viennent du live-fetch et pas du registre, dont le
// cache est vide en permanence pour ce backend (DiscoverAndRegister
// interroge sans identite, le wrapper repond alors la liste vide).
func TestFetchHellodataTools_AppelantAutoriseVoitLesTroisOutils(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get(EndUserEmailHeader); got != "alice@example.test" {
			t.Errorf("%s = %q", EndUserEmailHeader, got)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{"tools":[` +
			`{"name":"compter","description":"Compte les acheteurs."},` +
			`{"name":"echantillon","description":"Lit les acheteurs."},` +
			`{"name":"export_csv","description":"Rend le CSV."}` +
			`]}}`))
	}))
	defer s.Close()

	sg := &ScopedGateway{gatewayUsers: fakeUsers{"alice@example.test": "admin"}}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix, MessageURL: s.URL}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

	got := sg.fetchHellodataTools(ctx, b)
	if len(got) != 3 {
		t.Fatalf("%d outils, attendu 3", len(got))
	}
	attendus := []string{"hellodata_compter", "hellodata_echantillon", "hellodata_export_csv"}
	for i, nom := range attendus {
		if got[i].Name != nom {
			t.Errorf("outil %d = %q, attendu %q", i, got[i].Name, nom)
		}
		if !got[i].IsActive {
			t.Errorf("outil %q doit etre actif", got[i].Name)
		}
	}
	if got[0].Description != "Compte les acheteurs." {
		t.Errorf("Description = %q", got[0].Description)
	}
}
