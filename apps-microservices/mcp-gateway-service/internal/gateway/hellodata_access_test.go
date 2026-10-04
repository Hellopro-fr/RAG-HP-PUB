package gateway

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/mcp"
)

// Adresses fictives en .test : le depot est public.
const (
	hdAdmin   = "admin@example.test"
	hdGranted = "alice@example.test"
	hdLecteur = "bob@example.test"
	hdAutre   = "carol@example.test"
)

// newHellodataAccess : "srv-hd" est le backend hellodata (connu par son
// tool_prefix, sans template), "srv-plain" un serveur ordinaire. alice a un
// grant sur srv-hd, carol un grant sur srv-plain seulement.
func newHellodataAccess(serversErr error) *Neo4jAccess {
	return NewNeo4jAccess(
		&countingTemplates{rows: map[string]*db.Template{}},
		&countingServerSlugs{
			prefixes: map[string]string{"srv-hd": hellodataToolPrefix},
			err:      serversErr,
		},
		&countingUsers{rows: map[string]*db.GatewayUser{
			hdAdmin:   {Email: hdAdmin, Role: auth.RoleAdmin, IsAllowed: true},
			hdLecteur: {Email: hdLecteur, Role: "readonly", IsAllowed: true},
		}},
		&countingGrants{grants: map[string]map[string]bool{
			"srv-hd":    {hdGranted: true},
			"srv-plain": {hdAutre: true},
		}},
	)
}

func TestNeo4jAccess_HellodataRestreintAuxAdminsEtAuxGrants(t *testing.T) {
	cas := []struct {
		nom    string
		email  string
		attend bool
	}{
		{"admin", hdAdmin, true},
		{"grant sur le serveur hellodata", hdGranted, true},
		{"readonly sans grant", hdLecteur, false},
		{"grant sur un autre serveur seulement", hdAutre, false},
		{"sans email (token de scope, client_credentials)", "", false},
	}
	for _, c := range cas {
		// Deux chemins : le registre connait le tool_prefix (gateway), le
		// consentement ne tient que l'id (resolution par la base).
		t.Run(c.nom+" / backend du registre", func(t *testing.T) {
			b := &BackendServer{ID: "srv-hd", ToolPrefix: hellodataToolPrefix}
			if got := newHellodataAccess(nil).Allows(ctxWithEmail(c.email), b); got != c.attend {
				t.Errorf("Allows = %v, attendu %v", got, c.attend)
			}
		})
		t.Run(c.nom+" / id seul (consentement)", func(t *testing.T) {
			if got := newHellodataAccess(nil).AllowsEmail(c.email, "srv-hd", ""); got != c.attend {
				t.Errorf("AllowsEmail = %v, attendu %v", got, c.attend)
			}
		})
	}
}

// Controle positif du refus : le meme lecteur passe sur un serveur ordinaire,
// sinon les refus ci-dessus pourraient venir d'une politique qui refuse tout.
func TestNeo4jAccess_HellodataLeServeurOrdinaireResteOuvert(t *testing.T) {
	a := newHellodataAccess(nil)
	if !a.AllowsEmail(hdLecteur, "srv-plain", "") {
		t.Error("un serveur ordinaire doit rester ouvert a un readonly")
	}
	if a.Restricted(&BackendServer{ID: "srv-plain"}) {
		t.Error("srv-plain ne doit pas etre restreint")
	}
	if !a.Restricted(&BackendServer{ID: "srv-hd"}) {
		t.Error("srv-hd doit etre restreint par son tool_prefix lu en base")
	}
}

// Fail-closed : une erreur de lecture du serveur rend hellodata restreint ;
// l'admin et le titulaire du grant passent encore, le lecteur non.
func TestNeo4jAccess_HellodataErreurDeLectureFailClosed(t *testing.T) {
	a := newHellodataAccess(errors.New("db down"))
	if a.AllowsEmail(hdLecteur, "srv-hd", "") {
		t.Error("readonly sans grant doit etre refuse quand la lecture echoue")
	}
	if !a.AllowsEmail(hdAdmin, "srv-hd", "") {
		t.Error("l admin doit garder l acces quand la lecture echoue")
	}
	if !a.AllowsEmail(hdGranted, "srv-hd", "") {
		t.Error("le titulaire du grant doit garder l acces quand la lecture echoue")
	}
}

// Regression Step 0 : un grant hellodata faisait partir l'appel SANS
// X-End-User-Email, et le wrapper refusait l'appelant que le grant autorise.
func TestRequestHeaders_HellodataGrantGardeLIdentiteEtPoseGranted(t *testing.T) {
	sg := &ScopedGateway{
		gatewayUsers: fakeUsers{hdGranted: "readonly"},
		serverAuth:   &countingGrants{grants: map[string]map[string]bool{"srv-hd": {hdGranted: true}}},
	}
	b := &BackendServer{ID: "srv-hd", ToolPrefix: hellodataToolPrefix}

	h := sg.requestHeadersFor(ctxWithEmail(hdGranted), b)
	if h[EndUserEmailHeader] != hdGranted {
		t.Errorf("%s = %q, attendu %q", EndUserEmailHeader, h[EndUserEmailHeader], hdGranted)
	}
	if h[EndUserGrantedHeader] != "true" {
		t.Errorf("%s = %q, attendu \"true\"", EndUserGrantedHeader, h[EndUserGrantedHeader])
	}
	if h[EndUserRoleHeader] != "readonly" {
		t.Errorf("%s = %q, attendu readonly", EndUserRoleHeader, h[EndUserRoleHeader])
	}
}

// Sans grant sur CE serveur, pas d'en-tete Granted du tout : jamais "false",
// jamais de valeur par defaut.
func TestRequestHeaders_HellodataSansGrantPasDEnTeteGranted(t *testing.T) {
	sg := &ScopedGateway{
		gatewayUsers: fakeUsers{hdAutre: "readonly"},
		serverAuth:   &countingGrants{grants: map[string]map[string]bool{"srv-plain": {hdAutre: true}}},
	}
	b := &BackendServer{ID: "srv-hd", ToolPrefix: hellodataToolPrefix}

	h := sg.requestHeadersFor(ctxWithEmail(hdAutre), b)
	if v, ok := h[EndUserGrantedHeader]; ok {
		t.Errorf("%s = %q, attendu absent", EndUserGrantedHeader, v)
	}
	if h[EndUserEmailHeader] != hdAutre {
		t.Errorf("l email doit etre pose meme sans grant")
	}
}

// Un grant sur un autre backend ne diffuse pas Granted hors de hellodata.
func TestRequestHeaders_HellodataGrantedJamaisSurUnAutreBackend(t *testing.T) {
	sg := &ScopedGateway{
		gatewayUsers: fakeUsers{hdAutre: "readonly"},
		serverAuth:   &countingGrants{grants: map[string]map[string]bool{"srv-plain": {hdAutre: true}}},
	}
	h := sg.requestHeadersFor(ctxWithEmail(hdAutre), &BackendServer{ID: "srv-plain", ToolPrefix: "semrush"})
	if _, ok := h[EndUserGrantedHeader]; ok {
		t.Errorf("%s ne doit pas etre pose sur un backend non hellodata", EndUserGrantedHeader)
	}
}

// hellodataGateFixture : un gateway avec le controle d'acces cable et un
// backend hellodata dont l'amont enregistre chaque requete recue.
type hellodataGateFixture struct {
	sg      *ScopedGateway
	mu      sync.Mutex
	recues  []http.Header
	methode []string
}

func newHellodataGateFixture(t *testing.T) *hellodataGateFixture {
	t.Helper()
	f := &hellodataGateFixture{}
	amont := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Method string `json:"method"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)
		f.mu.Lock()
		f.recues = append(f.recues, r.Header.Clone())
		f.methode = append(f.methode, req.Method)
		f.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		if req.Method == "tools/list" {
			_, _ = w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"compter"}]}}`))
			return
		}
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{}}`))
	}))
	t.Cleanup(amont.Close)

	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-hd", MessageURL: amont.URL, ToolPrefix: hellodataToolPrefix})
	gw := New("gw", "1.0", reg)
	grants := &countingGrants{grants: map[string]map[string]bool{"srv-hd": {hdGranted: true}}}
	users := &countingUsers{rows: map[string]*db.GatewayUser{
		hdAdmin:   {Email: hdAdmin, Role: auth.RoleAdmin, IsAllowed: true},
		hdGranted: {Email: hdGranted, Role: "readonly", IsAllowed: true},
		hdLecteur: {Email: hdLecteur, Role: "readonly", IsAllowed: true},
	}}
	gw.SetGatewayUserFinder(users)
	gw.SetServerAuthorizer(grants)
	gw.SetNeo4jAccess(NewNeo4jAccess(&countingTemplates{}, &countingServerSlugs{}, users, grants))
	f.sg = NewScopedGateway(gw, map[string]bool{"srv-hd": true}, nil, nil)
	return f
}

func (f *hellodataGateFixture) appeler(t *testing.T, email, method string, params any) *mcp.Response {
	t.Helper()
	req := &mcp.Request{JSONRPC: "2.0", ID: json.RawMessage(`1`), Method: method}
	if params != nil {
		raw, err := json.Marshal(params)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		req.Params = raw
	}
	return f.sg.Handle(ctxWithEmail(email), req)
}

func (f *hellodataGateFixture) nbRecues() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.recues)
}

func TestScopedGateway_HellodataRefuseSansAtteindreLeBackend(t *testing.T) {
	for _, email := range []string{hdLecteur, ""} {
		t.Run("appelant "+email, func(t *testing.T) {
			f := newHellodataGateFixture(t)

			list := f.appeler(t, email, "tools/list", nil)
			if n := len(listedNames(t, list)); n != 0 {
				t.Errorf("tools/list : %d outils, attendu 0", n)
			}
			call := f.appeler(t, email, "tools/call", mcp.CallToolParams{Name: "hellodata_compter"})
			// Le refus doit venir du controle d'acces, pas d'un outil
			// introuvable : sinon ce test passerait sans controle du tout.
			if call.Error == nil || call.Error.Message != Neo4jAccessDeniedMessage {
				t.Errorf("tools/call = %+v, attendu le refus %q", call.Error, Neo4jAccessDeniedMessage)
			}
			if n := f.nbRecues(); n != 0 {
				t.Errorf("le backend a recu %d requete(s), attendu 0 (ni live-fetch ni forward)", n)
			}
		})
	}
}

// Controle positif : le titulaire du grant voit l'outil et son appel part
// avec son identite et Granted ; l'admin aussi, sans Granted.
func TestScopedGateway_HellodataGrantEtAdminAtteignentLeBackend(t *testing.T) {
	cas := []struct {
		email   string
		granted string
	}{
		{hdGranted, "true"},
		{hdAdmin, ""},
	}
	for _, c := range cas {
		t.Run(c.email, func(t *testing.T) {
			f := newHellodataGateFixture(t)
			if !listedNames(t, f.appeler(t, c.email, "tools/list", nil))["hellodata_compter"] {
				t.Fatal("tools/list doit montrer hellodata_compter")
			}
			call := f.appeler(t, c.email, "tools/call", mcp.CallToolParams{Name: "hellodata_compter"})
			if call.Error != nil {
				t.Fatalf("tools/call refuse : %+v", call.Error)
			}
			f.mu.Lock()
			defer f.mu.Unlock()
			if len(f.recues) != 2 || f.methode[1] != "tools/call" {
				t.Fatalf("requetes recues = %v, attendu [tools/list tools/call]", f.methode)
			}
			h := f.recues[1]
			if h.Get(EndUserEmailHeader) != c.email {
				t.Errorf("%s = %q", EndUserEmailHeader, h.Get(EndUserEmailHeader))
			}
			if h.Get(EndUserGrantedHeader) != c.granted {
				t.Errorf("%s = %q, attendu %q", EndUserGrantedHeader, h.Get(EndUserGrantedHeader), c.granted)
			}
		})
	}
}
