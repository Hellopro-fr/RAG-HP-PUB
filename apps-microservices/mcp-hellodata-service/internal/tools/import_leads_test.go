package tools

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"mcp-hellodata/internal/hellodata"
)

// Spec 2026-10-09-mcp-hellodata-import-et-leads-design.md : colonnes et
// simulation sur recup_acheteur, inscrire_contacts, date_reponse,
// marquer_leads.

func TestRecupAcheteur_ColonnesTransmises(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":1,"selectionnes":0,"exclus":{},"epuise":true}}`, 200),
		wh.serveur(t, `{}`, 200))

	args := strings.Replace(argsRecupValides, `"n": 20,`, `"n": 20, "colonnes": ["raison_sociale", "mobile"],`, 1)
	texte(t, appelOutil(t, h, alice, "recup_acheteur", args))

	var envoye struct {
		Colonnes    []string `json:"colonnes"`
		Restreintes bool     `json:"colonnes_restreintes_autorisees"`
		Simulation  *bool    `json:"simulation"`
	}
	if err := json.Unmarshal([]byte(bo.corps[0]), &envoye); err != nil {
		t.Fatalf("corps illisible: %v", err)
	}
	if strings.Join(envoye.Colonnes, ",") != "raison_sociale,mobile" || !envoye.Restreintes {
		t.Errorf("corps = %s", bo.corps[0])
	}
	if envoye.Simulation != nil {
		t.Errorf("simulation transmise sans etre demandee: %s", bo.corps[0])
	}
}

// Sans colonnes, le corps reste celui d'avant : le moteur rend le CSV
// historique a 8 colonnes.
func TestRecupAcheteur_SansColonnesCorpsInchange(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":1,"selectionnes":0,"exclus":{},"epuise":true}}`, 200),
		wh.serveur(t, `{}`, 200))
	texte(t, appelOutil(t, h, alice, "recup_acheteur", argsRecupValides))
	for _, champ := range []string{`"colonnes"`, `"simulation"`} {
		if strings.Contains(bo.corps[0], champ) {
			t.Errorf("%s present sans avoir ete demande: %s", champ, bo.corps[0])
		}
	}
}

func TestRecupAcheteur_ColonneInconnueRefuseeAvantReseau(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
	args := strings.Replace(argsRecupValides, `"n": 20,`, `"n": 20, "colonnes": ["telephone_fixe"],`, 1)
	r := appelOutil(t, h, alice, "recup_acheteur", args)
	if r.Error == nil || !strings.HasPrefix(r.Error.Message, "colonne_inconnue") {
		t.Errorf("erreur = %+v", r.Error)
	}
	if bo.nb() != 0 {
		t.Errorf("aucun appel BO attendu, %d", bo.nb())
	}
}

func TestRecupAcheteur_Simulation(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":0,"selectionnes":5,"exclus":{"ne_plus_contacter":1},"fiches_parcourues":40,"epuise":true,"simulation":true}}`, 200),
		wh.serveur(t, `{}`, 200))

	args := strings.Replace(argsRecupValides, `"n": 20,`, `"n": 20, "simulation": true,`, 1)
	sortie := texte(t, appelOutil(t, h, alice, "recup_acheteur", args))

	if !strings.Contains(bo.corps[0], `"simulation":true`) {
		t.Errorf("simulation non transmise: %s", bo.corps[0])
	}
	var s sortieRecup
	if err := json.Unmarshal([]byte(sortie), &s); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	// 5 selectionnes sans CSV : normal en simulation, pas une panne.
	if !s.Simulation || s.Selectionnes != 5 || s.URLCSV != "" || s.Avertissement != "" {
		t.Errorf("sortie = %+v", s)
	}
}

// Un moteur qui ignore le drapeau a REELLEMENT reserve : la sortie doit le
// dire et rendre le CSV, pas se presenter comme un apercu.
func TestRecupAcheteur_SimulationIgnoreeParLeMoteur(t *testing.T) {
	reponse, _ := json.Marshal(map[string]interface{}{
		"code": 200,
		"response": map[string]interface{}{
			"id_campagne": 4, "selectionnes": 1, "exclus": map[string]int{}, "epuise": true,
			"csv": "\xEF\xBB\xBFtelephone_normalise\n0612345678\n",
		},
	})
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, string(reponse), 200), wh.serveur(t, `{}`, 200))

	args := strings.Replace(argsRecupValides, `"n": 20,`, `"n": 20, "simulation": true,`, 1)
	var s sortieRecup
	if err := json.Unmarshal([]byte(texte(t, appelOutil(t, h, alice, "recup_acheteur", args))), &s); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if s.Simulation || !strings.HasPrefix(s.Avertissement, "simulation_non_supportee") || s.URLCSV == "" {
		t.Errorf("sortie = %+v", s)
	}
}

const argsInscriptionValides = `{
	"campagne": {"code": "EDF_20261007_P1", "nom": "EDF Commerce alimentaire", "canal": "sms", "date_campagne": "2026-10-07"},
	"contacts": [{"telephone": "06 12 34 56 78"}, {"id_acheteur": 42}]
}`

func contacts(n int) string {
	return `{"campagne":{"code":"c","nom":"n","canal":"sms","date_campagne":"2026-10-07"},"contacts":[` +
		strings.TrimSuffix(strings.Repeat(`{"telephone":"0612345678"},`, n), ",") + `]}`
}

func TestInscrireContacts_RefusAvantReseau(t *testing.T) {
	cas := []struct{ nom, args, code string }{
		{"aucun contact", contacts(0), "contacts_vides"},
		{"trop de contacts", contacts(ContactsMax + 1), "trop_de_contacts"},
		{"deux identifiants", strings.Replace(argsInscriptionValides, `{"id_acheteur": 42}`, `{"telephone": "0611111111", "id_acheteur": 42}`, 1), "contact_invalide"},
		{"aucun identifiant", strings.Replace(argsInscriptionValides, `{"id_acheteur": 42}`, `{"telephone": " "}`, 1), "contact_invalide"},
		{"id negatif", strings.Replace(argsInscriptionValides, `42`, `-3`, 1), "contact_invalide"},
		{"date future", strings.Replace(argsInscriptionValides, `2026-10-07`, `2099-01-01`, 1), "date_future"},
		{"canal email", strings.Replace(argsInscriptionValides, `"sms"`, `"email"`, 1), "campagne_invalide"},
		{"date illisible", strings.Replace(argsInscriptionValides, `2026-10-07`, `07/10/2026`, 1), "campagne_invalide"},
		{"telephone numerique", strings.Replace(argsInscriptionValides, `"06 12 34 56 78"`, `612345678`, 1), "arguments illisibles"},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			bo, wh := &amont{}, &amont{}
			h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
			r := appelOutil(t, h, alice, "inscrire_contacts", c.args)
			if r.Error == nil || !strings.HasPrefix(r.Error.Message, c.code) {
				t.Errorf("erreur = %+v, attendu le code %q", r.Error, c.code)
			}
			if bo.nb()+wh.nb() != 0 {
				t.Errorf("aucun appel reseau attendu, BO=%d webhook=%d", bo.nb(), wh.nb())
			}
		})
	}
	// Controle positif : 2000 contacts exactement passent la validation.
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{"code":200,"response":{"inscrits":1}}`, 200), wh.serveur(t, `{}`, 200))
	if r := appelOutil(t, h, alice, "inscrire_contacts", contacts(ContactsMax)); r.Error != nil || bo.nb() != 1 {
		t.Errorf("2000 contacts: erreur = %+v, appels BO = %d", r.Error, bo.nb())
	}
}

func TestInscrireContacts_VersLeBO(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":7,"campagne_creee":true,"inscrits":1,"inconnus":["06 12 34 56 78"]}}`, 200),
		wh.serveur(t, `{}`, 200))

	args := strings.Replace(argsInscriptionValides, `"contacts"`, `"cree_par": "pirate@example.test", "contacts"`, 1)
	sortie := texte(t, appelOutil(t, h, alice, "inscrire_contacts", args))

	if wh.nb() != 0 {
		t.Errorf("le webhook ne doit pas etre appele par inscrire_contacts")
	}
	if bo.nb() != 1 || bo.actions[0] != "inscrire_contacts" || bo.auth[0] != "Bearer jeton-bo" {
		t.Fatalf("BO: actions %v auth %v", bo.actions, bo.auth)
	}
	var envoye hellodata.DemandeInscription
	if err := json.Unmarshal([]byte(bo.corps[0]), &envoye); err != nil {
		t.Fatalf("corps illisible: %v", err)
	}
	if envoye.CreePar != "alice@example.test" || envoye.Campagne.DateCampagne != "2026-10-07" ||
		len(envoye.Contacts) != 2 || envoye.Contacts[0].Telephone != "06 12 34 56 78" || envoye.Contacts[1].IDAcheteur != 42 {
		t.Errorf("corps = %s", bo.corps[0])
	}
	// Le numero est transmis tel que recu : la normalisation est au moteur.
	if strings.Contains(bo.corps[0], `"id_acheteur":0`) || strings.Contains(bo.corps[0], `"telephone":""`) {
		t.Errorf("identifiant vide transmis: %s", bo.corps[0])
	}
	var res hellodata.Inscription
	if err := json.Unmarshal([]byte(sortie), &res); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if res.IDCampagne != 7 || !res.CampagneCreee || res.Inscrits != 1 || len(res.Inconnus) != 1 {
		t.Errorf("resultat = %+v", res)
	}
	for nom, l := range map[string][]string{"invalides": res.Invalides, "ne_plus_contacter": res.NePlusContacter} {
		if l == nil {
			t.Errorf("%s doit etre [] et non null: %s", nom, sortie)
		}
	}
}

func TestEnregistrerReponses_DateReponse(t *testing.T) {
	avecDate := func(d string) string {
		return `{"code_campagne":"c","reponses":[{"telephone":"0612345678","reponse_brute":"oui","categorie":"positive","date_reponse":"` + d + `"}]}`
	}
	for _, d := range []string{"2099-01-01", "08/10/2026", "2026-10-08T10:00:00"} {
		t.Run("refus "+d, func(t *testing.T) {
			bo, wh := &amont{}, &amont{}
			h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
			r := appelOutil(t, h, alice, "enregistrer_reponses", avecDate(d))
			if r.Error == nil || !strings.HasPrefix(r.Error.Message, "date_reponse_invalide") {
				t.Errorf("erreur = %+v", r.Error)
			}
			if wh.nb() != 0 {
				t.Errorf("aucun appel webhook attendu")
			}
		})
	}
	for _, d := range []string{"2026-10-08", "2026-10-08 14:32:00"} {
		t.Run("transmise "+d, func(t *testing.T) {
			bo, wh := &amont{}, &amont{}
			h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{"code":200,"response":{"mis_a_jour":1}}`, 200))
			texte(t, appelOutil(t, h, alice, "enregistrer_reponses", avecDate(d)))
			if !strings.Contains(wh.corps[0], `"date_reponse":"`+d+`"`) {
				t.Errorf("corps = %s", wh.corps[0])
			}
		})
	}
	// Sans date_reponse, le champ n'est pas transmis : le webhook prend NOW().
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{"code":200,"response":{"mis_a_jour":1}}`, 200))
	texte(t, appelOutil(t, h, alice, "enregistrer_reponses", reponses(1, "positive")))
	if strings.Contains(wh.corps[0], "date_reponse") {
		t.Errorf("date_reponse transmise sans etre fournie: %s", wh.corps[0])
	}
}

func leads(n int) string {
	return `{"code_campagne":"c","leads":[` +
		strings.TrimSuffix(strings.Repeat(`{"telephone":"0612345678"},`, n), ",") + `]}`
}

func TestMarquerLeads_RefusAvantReseau(t *testing.T) {
	cas := []struct{ nom, args, code string }{
		{"aucun lead", leads(0), "leads_vides"},
		{"trop de leads", leads(LeadsMax + 1), "trop_de_leads"},
		{"code absent", `{"leads":[{"telephone":"0612345678"}]}`, "code_campagne_invalide"},
		{"telephone absent", `{"code_campagne":"c","leads":[{"date_transmission":"2026-10-08"}]}`, "telephone_manquant"},
		{"date future", `{"code_campagne":"c","leads":[{"telephone":"06","date_transmission":"2099-01-01"}]}`, "date_transmission_invalide"},
		{"date illisible", `{"code_campagne":"c","leads":[{"telephone":"06","date_transmission":"demain"}]}`, "date_transmission_invalide"},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			bo, wh := &amont{}, &amont{}
			h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
			r := appelOutil(t, h, alice, "marquer_leads", c.args)
			if r.Error == nil || !strings.HasPrefix(r.Error.Message, c.code) {
				t.Errorf("erreur = %+v, attendu le code %q", r.Error, c.code)
			}
			if bo.nb()+wh.nb() != 0 {
				t.Errorf("aucun appel reseau attendu, BO=%d webhook=%d", bo.nb(), wh.nb())
			}
		})
	}
	// Controle positif : 500 leads exactement passent la validation.
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{"code":200,"response":{"marques":500}}`, 200))
	if r := appelOutil(t, h, alice, "marquer_leads", leads(LeadsMax)); r.Error != nil || wh.nb() != 1 {
		t.Errorf("500 leads: erreur = %+v, appels webhook = %d", r.Error, wh.nb())
	}
}

func TestMarquerLeads_VersLeWebhook(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{}`, 200),
		wh.serveur(t, `{"code":200,"response":{"marques":1,"non_positifs":["0611111111"]}}`, 200))

	sortie := texte(t, appelOutil(t, h, alice, "marquer_leads",
		`{"code_campagne":"EDF_20261007_P1","leads":[{"telephone":"0612345678","date_transmission":"2026-10-08"},{"telephone":"0611111111"}]}`))

	if bo.nb() != 0 {
		t.Errorf("le BO ne doit pas etre appele par marquer_leads")
	}
	if wh.nb() != 1 || wh.actions[0] != "marquer_leads" || wh.auth[0] != "Bearer jeton-webhook" {
		t.Fatalf("webhook: actions %v auth %v", wh.actions, wh.auth)
	}
	if !strings.Contains(wh.corps[0], `"date_transmission":"2026-10-08"`) {
		t.Errorf("corps = %s", wh.corps[0])
	}
	var res hellodata.ResultatLeads
	if err := json.Unmarshal([]byte(sortie), &res); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if res.Marques != 1 || len(res.NonPositifs) != 1 || res.Inconnus == nil || res.HorsCampagne == nil {
		t.Errorf("resultat = %+v (listes vides attendues [] et non null)", res)
	}
}

func TestBilanCampagnes_LeadsTransmis(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"campagnes":[{"code":"c","envoyes":10,"positive":3,"leads_transmis":2}]}}`, 200),
		wh.serveur(t, `{}`, 200))
	if sortie := texte(t, appelOutil(t, h, alice, "bilan_campagnes", `{}`)); !strings.Contains(sortie, `"leads_transmis": 2`) {
		t.Errorf("sortie = %s", sortie)
	}
}

// La borne du futur tolere le lendemain UTC : a 00:30 a Paris (22:30 UTC
// la veille), « aujourd'hui » pour l'utilisateur est demain pour le
// conteneur.
func TestProblemeDate(t *testing.T) {
	avant := maintenant
	t.Cleanup(func() { maintenant = avant })
	maintenant = func() time.Time { return time.Date(2026, 10, 9, 22, 30, 0, 0, time.UTC) }

	cas := []struct {
		date      string
		avecHeure bool
		ok        bool
	}{
		{"2026-10-07", false, true},
		{"2026-10-10", false, true},  // lendemain UTC : aujourd'hui a Paris
		{"2026-10-11", false, false}, // futur
		{"2026-10-10 23:59:59", true, true},
		{"2026-10-11 00:00:00", true, false},
		{"2026-10-08 14:00:00", false, false}, // heure non admise ici
		{"2026-13-01", false, false},
		{"", true, false},
	}
	for _, c := range cas {
		if got := problemeDate(c.date, c.avecHeure) == ""; got != c.ok {
			t.Errorf("problemeDate(%q, %v) accepte=%v, attendu %v", c.date, c.avecHeure, got, c.ok)
		}
	}
}
