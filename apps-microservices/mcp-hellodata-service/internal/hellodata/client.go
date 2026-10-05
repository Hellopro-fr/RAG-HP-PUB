// Package hellodata parle au moteur /admin/mcp/hellodata.
//
// Le contrat est celui que mcp-gateway-service/internal/bddcatalog utilise
// deja : Bearer, enveloppe {code, response}, et un budget de temps
// DIFFERENT par endpoint — un comptage exact et un echantillon n'ont
// aucune raison de partager la meme patience.
package hellodata

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// Budgets par endpoint, repris de la spec section 8.
const (
	BudgetComptageApproche = 20 * time.Second
	BudgetComptageExact    = 120 * time.Second
	BudgetEchantillon      = 30 * time.Second
	// recup_acheteur parcourt jusqu'a 100 000 fiches par appel.
	BudgetRecup    = 120 * time.Second
	BudgetBilan    = 20 * time.Second
	BudgetReponses = 30 * time.Second
)

// Plafond de lecture d'une reponse JSON. Un moteur qui deraille ne doit
// pas pouvoir epuiser la memoire du wrapper.
const corpsMax = 16 << 20

// Prefixe de la ligne sentinelle qui cloture un export CSV.
const sentinelleExport = "# fin-export;"

// BOM UTF-8. Le moteur l'emet TOUJOURS en tete de l'export — sans lui
// Excel affiche des mojibake — donc c'est au client de le tolerer.
const bomUTF8 = "\xEF\xBB\xBF"

type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

// Le http.Client ne porte pas de Timeout : chaque appel pose le sien par
// contexte, sinon le budget le plus court s'appliquerait a tous.
func Nouveau(baseURL, token string) *Client {
	return &Client{baseURL: baseURL, token: token, http: &http.Client{}}
}

type enveloppe struct {
	Code     int             `json:"code"`
	Response json.RawMessage `json:"response"`
}

type erreurCorps struct {
	Erreur  string `json:"erreur"`
	Message string `json:"message"`
}

func (c *Client) Compter(ctx context.Context, d Demande) (Comptage, error) {
	budget := BudgetComptageApproche
	if d.Exact {
		budget = BudgetComptageExact
	}
	var out Comptage
	err := c.poster(ctx, "comptage", d, budget, &out)
	return out, err
}

func (c *Client) Echantillon(ctx context.Context, d Demande) (Echantillon, error) {
	var out Echantillon
	err := c.poster(ctx, "echantillon", d, BudgetEchantillon, &out)
	return out, err
}

// RecupAcheteur selectionne et inscrit n acheteurs dans une campagne (BO).
func (c *Client) RecupAcheteur(ctx context.Context, d DemandeRecup) (Recuperation, error) {
	var out Recuperation
	err := c.poster(ctx, "recup_acheteur", d, BudgetRecup, &out)
	out.URLCSV = c.lienValide(out.URLCSV)
	return out, err
}

// BilanCampagnes liste les campagnes, ou la seule campagne code si non vide (BO).
func (c *Client) BilanCampagnes(ctx context.Context, code string) (Bilan, error) {
	var out Bilan
	corps := map[string]string{}
	if code != "" {
		corps["code"] = code
	}
	err := c.poster(ctx, "bilan_campagnes", corps, BudgetBilan, &out)
	return out, err
}

// EnregistrerReponses ecrit les reponses d'une campagne. Appele sur le
// client du webhook FRONT (partenaires_externes/mcp/hellodata), qui parle
// le meme contrat que le BO : Bearer, ?action=, enveloppe {code, response}.
func (c *Client) EnregistrerReponses(ctx context.Context, d DemandeReponses) (ResultatReponses, error) {
	var out ResultatReponses
	err := c.poster(ctx, "enregistrer_reponses", d, BudgetReponses, &out)
	return out, err
}

// ExporterCSV rend le CSV d'UNE page, deja lu en entier, plus le curseur
// suivant. Une page est plafonnee a 2000 lignes, donc la lire en memoire
// est borne par construction — et c'est ce qui permet au wrapper de rendre
// next_cursor au LLM des l'appel de l'outil.
//
// Rend une erreur si la sentinelle manque : une reponse coupee ne doit pas
// passer pour un CSV complet.
func (c *Client) ExporterCSV(ctx context.Context, d Demande) (PageCSV, error) {
	ctx, annule := context.WithTimeout(ctx, BudgetEchantillon)
	defer annule()

	brut, err := json.Marshal(d)
	if err != nil {
		return PageCSV{}, fmt.Errorf("export: encodage: %w", err)
	}
	req, err := c.requete(ctx, http.MethodPost, "export", nil, brut)
	if err != nil {
		return PageCSV{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return PageCSV{}, fmt.Errorf("export: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return PageCSV{}, c.erreurDepuis(resp)
	}

	corps, err := io.ReadAll(io.LimitReader(resp.Body, corpsMax))
	if err != nil {
		return PageCSV{}, fmt.Errorf("export: lecture: %w", err)
	}
	page, err := analyserPageCSV(corps)
	if err != nil {
		return PageCSV{}, err
	}
	page.Lien = c.lienValide(resp.Header.Get("X-Hellodata-Lien"))
	return page, nil
}

// lienValide garde un lien de telechargement du moteur seulement s'il pointe
// le MEME schema et le MEME hote que HELLODATA_BASE_URL (https exige, sauf si
// la base elle-meme est en http). Tout autre lien est ignore : l'outil
// retombe sur /download plutot que de rendre au LLM une URL etrangere.
func (c *Client) lienValide(lien string) string {
	lien = strings.TrimSpace(lien)
	if lien == "" {
		return ""
	}
	base, err := url.Parse(c.baseURL)
	if err != nil {
		return ""
	}
	u, err := url.Parse(lien)
	if err != nil || u.User != nil || u.Host == "" {
		return ""
	}
	if !strings.EqualFold(u.Scheme, base.Scheme) || !strings.EqualFold(u.Host, base.Host) {
		return ""
	}
	if u.Scheme != "https" && u.Scheme != "http" {
		return ""
	}
	return lien
}

// analyserPageCSV separe le contenu CSV de la ligne sentinelle finale
// "# fin-export;<lignes>;<next_cursor>". Son absence signale une reponse
// coupee en cours de transfert.
//
// Sur une SELECTION VIDE, la sortie entiere vaut BOM + sentinelle : ni
// en-tete ni donnees, donc le BOM colle au debut de la derniere ligne. Il
// est retire avant la reconnaissance du prefixe, sinon un filtre
// parfaitement legitime qui ne ramene rien serait rendu comme une reponse
// tronquee. Il reste en revanche en tete de Contenu quand des donnees
// suivent : c'est ce contenu-la qui est servi au telechargement, et le BOM
// est ce qui evite les mojibake dans Excel.
func analyserPageCSV(corps []byte) (PageCSV, error) {
	fin := bytes.TrimRight(corps, "\n")
	var derniereLigne, avantSentinelle []byte
	if idx := bytes.LastIndexByte(fin, '\n'); idx == -1 {
		derniereLigne = bytes.TrimPrefix(fin, []byte(bomUTF8))
	} else {
		derniereLigne = fin[idx+1:]
		avantSentinelle = fin[:idx]
	}
	if !bytes.HasPrefix(derniereLigne, []byte(sentinelleExport)) {
		return PageCSV{}, fmt.Errorf("export: sentinelle de fin absente (reponse tronquee)")
	}

	champs := strings.Split(strings.TrimPrefix(string(derniereLigne), sentinelleExport), ";")
	if len(champs) != 2 {
		return PageCSV{}, fmt.Errorf("export: sentinelle malformee: %q", derniereLigne)
	}
	lignes, err := strconv.Atoi(champs[0])
	if err != nil {
		return PageCSV{}, fmt.Errorf("export: nombre de lignes invalide dans la sentinelle: %w", err)
	}

	var curseur *int
	if champs[1] != "" {
		v, err := strconv.Atoi(champs[1])
		if err != nil {
			return PageCSV{}, fmt.Errorf("export: next_cursor invalide dans la sentinelle: %w", err)
		}
		curseur = &v
	}

	return PageCSV{
		Contenu:    avantSentinelle,
		Lignes:     lignes,
		NextCursor: curseur,
		HasMore:    curseur != nil,
	}, nil
}

func (c *Client) poster(ctx context.Context, action string, corps interface{}, budget time.Duration, out interface{}) error {
	ctx, annule := context.WithTimeout(ctx, budget)
	defer annule()
	brut, err := json.Marshal(corps)
	if err != nil {
		return fmt.Errorf("%s: encodage: %w", action, err)
	}
	req, err := c.requete(ctx, http.MethodPost, action, nil, brut)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	return c.executer(req, action, out)
}

func (c *Client) requete(ctx context.Context, methode, action string, params map[string]string, corps []byte) (*http.Request, error) {
	var lecteur io.Reader
	if corps != nil {
		lecteur = bytes.NewReader(corps)
	}
	req, err := http.NewRequestWithContext(ctx, methode, c.baseURL+"/index.php", lecteur)
	if err != nil {
		return nil, fmt.Errorf("%s: construction: %w", action, err)
	}
	q := req.URL.Query()
	q.Set("action", action)
	for k, v := range params {
		q.Set(k, v)
	}
	req.URL.RawQuery = q.Encode()
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")
	return req, nil
}

func (c *Client) executer(req *http.Request, action string, out interface{}) error {
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("%s: %w", action, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return c.erreurDepuis(resp)
	}
	brut, err := io.ReadAll(io.LimitReader(resp.Body, corpsMax))
	if err != nil {
		return fmt.Errorf("%s: lecture: %w", action, err)
	}
	var env enveloppe
	if err := json.Unmarshal(brut, &env); err != nil || env.Response == nil {
		// Une page HTML d'Apache ou une redirection de session arrive ici.
		// La traiter comme un resultat vide la ferait passer pour un
		// succes ; on echoue explicitement.
		return fmt.Errorf("%s: reponse hors contrat (enveloppe {code, response} attendue)", action)
	}
	if err := json.Unmarshal(env.Response, out); err != nil {
		return fmt.Errorf("%s: decodage du payload: %w", action, err)
	}
	return nil
}

func (c *Client) erreurDepuis(resp *http.Response) error {
	brut, _ := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	var env enveloppe
	if json.Unmarshal(brut, &env) == nil && env.Response != nil {
		var e erreurCorps
		if json.Unmarshal(env.Response, &e) == nil && e.Erreur != "" {
			return &ErreurMoteur{Code: e.Erreur, Message: e.Message}
		}
	}
	return &ErreurMoteur{
		Code:    "moteur_indisponible",
		Message: fmt.Sprintf("statut HTTP %d", resp.StatusCode),
	}
}
