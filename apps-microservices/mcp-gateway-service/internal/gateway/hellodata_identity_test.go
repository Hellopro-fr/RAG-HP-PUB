package gateway

import (
	"context"
	"testing"

	"mcp-gateway/internal/scopetoken"
)

func TestRequestHeadersFor_HellodataInjecteIdentiteEtRole(t *testing.T) {
	sg := &ScopedGateway{gatewayUsers: fakeUsers{"alice@example.test": "readonly"}}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

	h := sg.requestHeadersFor(ctx, b)
	if h[EndUserEmailHeader] != "alice@example.test" {
		t.Errorf("%s = %q", EndUserEmailHeader, h[EndUserEmailHeader])
	}
	if h[EndUserRoleHeader] != "readonly" {
		t.Errorf("%s = %q", EndUserRoleHeader, h[EndUserRoleHeader])
	}
}

// Les autres backends ne doivent RIEN recevoir : on n'elargit pas la
// diffusion de l'identite au passage.
func TestRequestHeadersFor_IdentiteAbsentePourLesAutresBackends(t *testing.T) {
	sg := &ScopedGateway{gatewayUsers: fakeUsers{"alice@example.test": "admin"}}
	b := &BackendServer{ID: "autre", ToolPrefix: "semrush"}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

	h := sg.requestHeadersFor(ctx, b)
	if _, ok := h[EndUserRoleHeader]; ok {
		t.Errorf("%s ne doit pas etre pose sur un backend non hellodata", EndUserRoleHeader)
	}
}

// Fail-closed a l'emission : une resolution de role en echec n'envoie
// AUCUN en-tete de role. En aval, une valeur par defaut deviendrait un
// role effectif.
func TestRequestHeadersFor_HellodataRoleNonResoluNEnvoieRien(t *testing.T) {
	cas := []struct {
		nom   string
		users gatewayUserFinder
	}{
		{"depot non cable", nil},
		{"email absent du depot", fakeUsers{}},
		{"depot en erreur", errUsers{}},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			sg := &ScopedGateway{gatewayUsers: c.users}
			b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix}
			ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

			h := sg.requestHeadersFor(ctx, b)
			if v, ok := h[EndUserRoleHeader]; ok {
				t.Errorf("%s = %q, attendu absent", EndUserRoleHeader, v)
			}
			if h[EndUserEmailHeader] != "alice@example.test" {
				t.Errorf("l email doit rester pose meme sans role")
			}
		})
	}
}

// Sans identite sur le contexte — token de scope, client_credentials,
// sonde de sante — rien n'est pose. Le backend refusera, c'est voulu.
func TestRequestHeadersFor_HellodataSansIdentite(t *testing.T) {
	sg := &ScopedGateway{gatewayUsers: fakeUsers{}}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix}

	h := sg.requestHeadersFor(context.Background(), b)
	if _, ok := h[EndUserEmailHeader]; ok {
		t.Error("aucun en-tete d identite sans email sur le contexte")
	}
}
