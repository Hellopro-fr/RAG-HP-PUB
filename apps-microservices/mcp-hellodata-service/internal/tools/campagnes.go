package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"
	"unicode/utf8"

	"mcp-hellodata/internal/filtre"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// Bornes des outils de campagne (spec 2026-09-28-mcp-hellodata-campagnes-design.md).
const (
	// NMax : au-dela, appels repetes sur la meme campagne (decision C6).
	NMax = 2000
	// ReponsesMax : le webhook refuse au-dela, le LLM decoupe.
	ReponsesMax = 500
	// ContactsMax : liste deja envoyee inscrite en un appel (comme NMax).
	ContactsMax = 2000
	// LeadsMax : comme les reponses, le webhook refuse au-dela.
	LeadsMax = 500
	// CorpsReponsesMax : plafond du corps accepte par le webhook et par le
	// routeur du BO. Verifie ici pour refuser avant le reseau, avec un
	// message que le LLM corrige.
	CorpsReponsesMax = 256 << 10
	codeMax          = 64
	texteMax         = 255
)

var canaux = map[string]bool{"sms": true, "appel": true}

var categories = map[string]bool{
	"positive":             true,
	"negative_contactable": true,
	"negative_stop":        true,
}

// argsRecup ne porte volontairement aucun cree_par : un champ inconnu est
// ignore au decodage, et cree_par vient toujours de l'identite.
type argsRecup struct {
	Campagne   hellodata.Campagne `json:"campagne"`
	N          int                `json:"n"`
	Filtre     json.RawMessage    `json:"filtre"`
	Colonnes   []string           `json:"colonnes"`
	Simulation bool               `json:"simulation"`
}

// sortieRecup est ce que voit le LLM : la reponse du BO sans le CSV, plus
// le lien /download qui le sert.
type sortieRecup struct {
	IDCampagne       int            `json:"id_campagne"`
	CampagneCreee    bool           `json:"campagne_creee"`
	Selectionnes     int            `json:"selectionnes"`
	Exclus           map[string]int `json:"exclus"`
	FichesParcourues int            `json:"fiches_parcourues"`
	Epuise           bool           `json:"epuise"`
	URLCSV           string         `json:"url_csv,omitempty"`
	Simulation       bool           `json:"simulation,omitempty"`
	Avertissement    string         `json:"avertissement,omitempty"`
}

func (h *Handler) recupAcheteur(ctx context.Context, id Identite, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var a argsRecup
	if err := json.Unmarshal(brut, &a); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
	}
	if err := validerCampagne(a.Campagne); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
	}
	if a.N < 1 || a.N > NMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("n_hors_bornes: %d hors bornes 1..%d ; au-dela, rappeler sur la meme campagne", a.N, NMax))
	}
	a.Filtre = normaliserFiltre(a.Filtre)
	if errRep := validerFiltre(rpcID, a.Filtre); errRep != nil {
		return *errRep
	}
	droit := droitContacts(id)
	if err := validerColonnes(a.Colonnes, droit); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
	}

	res, err := h.client.RecupAcheteur(ctx, hellodata.DemandeRecup{
		Campagne: a.Campagne,
		N:        a.N,
		Filtre:   a.Filtre,
		// L'auteur est l'appelant authentifie, jamais un argument.
		CreePar:     id.Email,
		Colonnes:    a.Colonnes,
		Restreintes: droit,
		Simulation:  a.Simulation,
	})
	if err != nil {
		return erreurMoteur(rpcID, err)
	}

	sortie := sortieRecup{
		IDCampagne:       res.IDCampagne,
		CampagneCreee:    res.CampagneCreee,
		Selectionnes:     res.Selectionnes,
		Exclus:           res.Exclus,
		FichesParcourues: res.FichesParcourues,
		Epuise:           res.Epuise,
	}
	if a.Simulation && res.Simulation {
		// Rien n'a ete ecrit : ni CSV ni lien a rendre.
		sortie.Simulation = true
		return contenu(rpcID, sortie)
	}
	if a.Simulation {
		// Moteur anterieur au mode simulation : il a ignore le drapeau et
		// REELLEMENT reserve. Le dire plutot que presenter un apercu.
		log.Printf("[hellodata] recup_acheteur simulation ignoree par le moteur campagne=%s demandeur=%s selectionnes=%d", a.Campagne.Code, id.Email, res.Selectionnes)
		sortie.Avertissement = "simulation_non_supportee: le moteur ne connait pas encore le mode simulation ; " +
			"ces acheteurs ont ete REELLEMENT inscrits dans la campagne"
	}
	if res.Selectionnes > 0 && res.URLCSV != "" {
		// Lien signe du BO (download.php, 15 min, CSV regenere depuis edgb2b).
		log.Printf("[hellodata] recup_acheteur lien_bo campagne=%s demandeur=%s selectionnes=%d", a.Campagne.Code, id.Email, res.Selectionnes)
		sortie.URLCSV = res.URLCSV
		return contenu(rpcID, sortie)
	}
	if res.Selectionnes > 0 {
		if res.CSV == "" {
			log.Printf("[hellodata] recup_acheteur campagne=%s: %d selectionnes mais CSV absent", a.Campagne.Code, res.Selectionnes)
			return mcp.Echec(rpcID, mcp.CodeErreurInterne, "moteur_indisponible: CSV absent de la reponse")
		}
		jeton, err := h.jetons.Frapper([]byte(res.CSV))
		if err != nil {
			log.Printf("[hellodata] recup_acheteur: %v", err)
			return mcp.Echec(rpcID, mcp.CodeErreurInterne, "export_indisponible: reessayer plus tard")
		}
		// Seule trace d'une extraction de numeros de telephone : on la garde.
		log.Printf("[hellodata] recup_acheteur jeton=%s campagne=%s demandeur=%s selectionnes=%d", jeton, a.Campagne.Code, id.Email, res.Selectionnes)
		sortie.URLCSV = h.publicURL + "/download/" + jeton
	}
	return contenu(rpcID, sortie)
}

func (h *Handler) bilanCampagnes(ctx context.Context, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var a struct {
		Code string `json:"code"`
	}
	if len(brut) > 0 {
		if err := json.Unmarshal(brut, &a); err != nil {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
		}
	}
	if len(a.Code) > codeMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, fmt.Sprintf("code_invalide: plus de %d caracteres", codeMax))
	}
	res, err := h.client.BilanCampagnes(ctx, a.Code)
	if err != nil {
		return erreurMoteur(rpcID, err)
	}
	if res.Campagnes == nil {
		res.Campagnes = []hellodata.LigneBilan{}
	}
	return contenu(rpcID, res)
}

func (h *Handler) enregistrerReponses(ctx context.Context, id Identite, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var d hellodata.DemandeReponses
	if err := json.Unmarshal(brut, &d); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
	}
	if strings.TrimSpace(d.CodeCampagne) == "" || len(d.CodeCampagne) > codeMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("code_campagne_invalide: requis, %d caracteres au plus", codeMax))
	}
	if len(d.Reponses) == 0 {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "reponses_vides: au moins une reponse")
	}
	if len(d.Reponses) > ReponsesMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("trop_de_reponses: %d, maximum %d par appel ; decouper en plusieurs appels", len(d.Reponses), ReponsesMax))
	}
	for i, r := range d.Reponses {
		if strings.TrimSpace(r.Telephone) == "" {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, fmt.Sprintf("telephone_manquant: reponse %d", i))
		}
		if !categories[r.Categorie] {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
				fmt.Sprintf("categorie_invalide: reponse %d, %q (attendues: positive, negative_contactable, negative_stop)", i, r.Categorie))
		}
		if r.DateReponse != "" {
			if p := problemeDate(r.DateReponse, true); p != "" {
				return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
					fmt.Sprintf("date_reponse_invalide: reponse %d, %q : %s", i, r.DateReponse, p))
			}
		}
	}
	if corps, _ := json.Marshal(d); len(corps) > CorpsReponsesMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("corps_trop_gros: %d octets, maximum %d ; decouper en plusieurs appels", len(corps), CorpsReponsesMax))
	}

	res, err := h.webhook.EnregistrerReponses(ctx, d)
	if err != nil {
		return erreurMoteur(rpcID, err)
	}
	log.Printf("[hellodata] enregistrer_reponses campagne=%s demandeur=%s recues=%d mis_a_jour=%d", d.CodeCampagne, id.Email, len(d.Reponses), res.MisAJour)
	if res.Inconnus == nil {
		res.Inconnus = []string{}
	}
	if res.HorsCampagne == nil {
		res.HorsCampagne = []string{}
	}
	return contenu(rpcID, res)
}

// inscrireContacts enregistre une liste DEJA envoyee hors MCP : pas de
// parcours ni d'exclusion, un fait a historiser a sa date reelle. Le moteur
// rend les numeros qu'il ne sait pas rattacher.
func (h *Handler) inscrireContacts(ctx context.Context, id Identite, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var a struct {
		Campagne hellodata.Campagne  `json:"campagne"`
		Contacts []hellodata.Contact `json:"contacts"`
	}
	if err := json.Unmarshal(brut, &a); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
	}
	if err := validerCampagne(a.Campagne); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
	}
	if p := problemeDate(a.Campagne.DateCampagne, false); p != "" {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("date_future: date_campagne %q : %s ; inscrire_contacts enregistre un envoi deja fait", a.Campagne.DateCampagne, p))
	}
	if len(a.Contacts) == 0 {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "contacts_vides: au moins un contact")
	}
	if len(a.Contacts) > ContactsMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("trop_de_contacts: %d, maximum %d par appel ; decouper et rappeler sur la meme campagne", len(a.Contacts), ContactsMax))
	}
	for i, c := range a.Contacts {
		aTel := strings.TrimSpace(c.Telephone) != ""
		if aTel == (c.IDAcheteur != 0) || c.IDAcheteur < 0 {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
				fmt.Sprintf("contact_invalide: contact %d, exactement un de telephone / id_acheteur (entier positif)", i))
		}
	}
	d := hellodata.DemandeInscription{
		Campagne: a.Campagne,
		Contacts: a.Contacts,
		// L'auteur est l'appelant authentifie, jamais un argument.
		CreePar: id.Email,
	}
	if corps, _ := json.Marshal(d); len(corps) > CorpsReponsesMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("corps_trop_gros: %d octets, maximum %d ; decouper en plusieurs appels", len(corps), CorpsReponsesMax))
	}

	res, err := h.client.InscrireContacts(ctx, d)
	if err != nil {
		return erreurMoteur(rpcID, err)
	}
	log.Printf("[hellodata] inscrire_contacts campagne=%s demandeur=%s recus=%d inscrits=%d inconnus=%d invalides=%d",
		a.Campagne.Code, id.Email, len(a.Contacts), res.Inscrits, len(res.Inconnus), len(res.Invalides))
	for _, l := range []*[]string{&res.Inconnus, &res.Invalides, &res.NePlusContacter} {
		if *l == nil {
			*l = []string{}
		}
	}
	return contenu(rpcID, res)
}

// marquerLeads pose la date de transmission au client sur des suivis de
// reponse positive. Ecriture sur les reponses : webhook FRONT (decision C3).
func (h *Handler) marquerLeads(ctx context.Context, id Identite, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var d hellodata.DemandeLeads
	if err := json.Unmarshal(brut, &d); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
	}
	if strings.TrimSpace(d.CodeCampagne) == "" || len(d.CodeCampagne) > codeMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("code_campagne_invalide: requis, %d caracteres au plus", codeMax))
	}
	if len(d.Leads) == 0 {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "leads_vides: au moins un lead")
	}
	if len(d.Leads) > LeadsMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("trop_de_leads: %d, maximum %d par appel ; decouper en plusieurs appels", len(d.Leads), LeadsMax))
	}
	for i, l := range d.Leads {
		if strings.TrimSpace(l.Telephone) == "" {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, fmt.Sprintf("telephone_manquant: lead %d", i))
		}
		if l.DateTransmission != "" {
			if p := problemeDate(l.DateTransmission, true); p != "" {
				return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
					fmt.Sprintf("date_transmission_invalide: lead %d, %q : %s", i, l.DateTransmission, p))
			}
		}
	}
	if corps, _ := json.Marshal(d); len(corps) > CorpsReponsesMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("corps_trop_gros: %d octets, maximum %d ; decouper en plusieurs appels", len(corps), CorpsReponsesMax))
	}

	res, err := h.webhook.MarquerLeads(ctx, d)
	if err != nil {
		return erreurMoteur(rpcID, err)
	}
	log.Printf("[hellodata] marquer_leads campagne=%s demandeur=%s recus=%d marques=%d", d.CodeCampagne, id.Email, len(d.Leads), res.Marques)
	for _, l := range []*[]string{&res.Inconnus, &res.HorsCampagne, &res.NonPositifs} {
		if *l == nil {
			*l = []string{}
		}
	}
	return contenu(rpcID, res)
}

// maintenant est remplacable par les tests.
var maintenant = time.Now

// problemeDate rend "" pour une date passee bien formee, sinon la raison.
// Le conteneur tourne en UTC et l'utilisateur en Europe/Paris (jusqu'a 2 h
// d'avance) : une date est refusee seulement au-dela du lendemain UTC, pour
// ne jamais rejeter « aujourd'hui » a Paris. Le moteur refait le controle.
func problemeDate(s string, avecHeure bool) string {
	formats := []string{"2006-01-02"}
	attendu := "format AAAA-MM-JJ attendu"
	if avecHeure {
		formats = append(formats, "2006-01-02 15:04:05")
		attendu = "format AAAA-MM-JJ ou AAAA-MM-JJ HH:MM:SS attendu"
	}
	a, m, j := maintenant().UTC().Date()
	limite := time.Date(a, m, j+2, 0, 0, 0, 0, time.UTC)
	for _, f := range formats {
		if t, err := time.Parse(f, s); err == nil {
			if !t.Before(limite) {
				return "date dans le futur"
			}
			return ""
		}
	}
	return attendu
}

func validerCampagne(c hellodata.Campagne) error {
	if strings.TrimSpace(c.Code) == "" || len(c.Code) > codeMax {
		return fmt.Errorf("campagne_invalide: code requis, %d caracteres au plus", codeMax)
	}
	if strings.TrimSpace(c.Nom) == "" || utf8.RuneCountInString(c.Nom) > texteMax {
		return fmt.Errorf("campagne_invalide: nom requis, %d caracteres au plus", texteMax)
	}
	if !canaux[c.Canal] {
		return fmt.Errorf("campagne_invalide: canal %q (attendus: sms, appel)", c.Canal)
	}
	if utf8.RuneCountInString(c.Prestataire) > texteMax {
		return fmt.Errorf("campagne_invalide: prestataire, %d caracteres au plus", texteMax)
	}
	if _, err := time.Parse("2006-01-02", c.DateCampagne); err != nil {
		return fmt.Errorf("campagne_invalide: date_campagne %q, format AAAA-MM-JJ attendu", c.DateCampagne)
	}
	return nil
}

// normaliserFiltre accepte un filtre recu comme chaine JSON contenant
// l'objet (certains clients serialisent ainsi un parametre dont ils ne lisent
// pas le type) et rend l'objet brut. Tout le reste est rendu tel quel :
// validerFiltre / filtre.Valider tranchent ensuite. Le filtre normalise est
// aussi celui transmis au moteur, qui attend un objet.
func normaliserFiltre(brut json.RawMessage) json.RawMessage {
	t := bytes.TrimSpace(brut)
	if len(t) == 0 || t[0] != '"' {
		return brut
	}
	var interieur string
	if err := json.Unmarshal(t, &interieur); err != nil {
		return brut
	}
	return json.RawMessage(interieur)
}

// validerFiltre applique la validation structurelle commune. Les feuilles
// hist_* sont des feuilles ordinaires ici : leur place dans l'arbre
// (hist_hors_et_racine) est jugee par le compilateur du moteur.
func validerFiltre(rpcID json.RawMessage, brut json.RawMessage) *mcp.Reponse {
	if len(brut) == 0 {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre requis")
		return &r
	}
	var n filtre.Noeud
	if err := json.Unmarshal(brut, &n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre illisible: "+err.Error())
		return &r
	}
	if _, err := filtre.Valider(n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
		return &r
	}
	return nil
}
