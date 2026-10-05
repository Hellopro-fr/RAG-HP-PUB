package tools

import "mcp-hellodata/internal/mcp"

// TailleMax et TailleDefaut bornent la lecture. 2000 est le plafond de la
// spec ; 50 est un echantillon, pas une extraction.
const (
	TailleMax    = 2000
	TailleDefaut = 50
)

// schemaFiltre decrit l'arbre imbrique SANS $ref. Une reference
// "#/definitions/..." se resout depuis la racine de l'inputSchema, pas depuis
// la propriete : placee ici, elle etait cassee, et claude.ai envoyait alors
// filtre comme une chaine ("filtre illisible: cannot unmarshal string").
// Le type "object" explicite suffit aux clients ; la forme recursive est
// decrite en texte et validee cote serveur par filtre.Valider.
func schemaFiltre() map[string]interface{} {
	return map[string]interface{}{
		"type": "object",
		"description": "Arbre de filtres. Un noeud est soit un groupe " +
			"{operateur: ET|OU|NON, conditions: [noeuds]} (NON : exactement une condition, " +
			"1 a 20 conditions par groupe), soit une feuille {critere, comparateur, valeur}. " +
			"Exemple : {\"operateur\":\"ET\",\"conditions\":[{\"critere\":\"departement\"," +
			"\"comparateur\":\"dans\",\"valeur\":[\"75\"]}]}",
		"properties": map[string]interface{}{
			"operateur": map[string]interface{}{
				"type": "string", "enum": []string{"ET", "OU", "NON"},
			},
			"conditions": map[string]interface{}{
				"type":        "array",
				"items":       map[string]interface{}{"type": "object"},
				"minItems":    1,
				"maxItems":    20,
				"description": "Noeuds enfants, de meme forme que le filtre.",
			},
			"critere":     map[string]interface{}{"type": "string"},
			"comparateur": map[string]interface{}{"type": "string"},
			"valeur":      map[string]interface{}{},
		},
	}
}

// objet omet "required" quand rien n'est requis : un "required": null est
// refuse par les clients qui valident le schema.
func objet(props map[string]interface{}, requis ...string) map[string]interface{} {
	o := map[string]interface{}{"type": "object", "properties": props}
	if len(requis) > 0 {
		o["required"] = requis
	}
	return o
}

// Definitions rend les six outils exposes au LLM : trois de selection
// (compter, echantillon, export_csv) et trois de campagne (recup_acheteur,
// bilan_campagnes, enregistrer_reponses). hellodata_export_statut
// n'existe pas : l'export tient sur une seule page, plafonnee a 2000
// lignes, rendue directement par hellodata_export_csv.
//
// Les noms sont SANS le prefixe 'hellodata_' : c'est le gateway qui
// l'ajoute (tool_prefix = "hellodata", PrefixedToolName), comme
// bdd_query_readonly est le prefixe 'bdd' plus l'outil 'query_readonly'.
// Le renommer ici donnerait hellodata_hellodata_compter au LLM.
func Definitions() []mcp.Outil {
	colonnes := map[string]interface{}{
		"type":  "array",
		"items": map[string]interface{}{"type": "string", "enum": nomsColonnes()},
		"description": "Colonnes a restituer, choisies par l'utilisateur. Champs : " + listeColonnes() +
			". Non disponibles : " + nonDisponibles + ".",
	}
	blocage := map[string]interface{}{
		"type": "integer", "enum": []int{1, 2, 3, 4, 5, 7, 8},
		"description": "Dedoublonnage : 1 aucun, 2 ou 3 par SIREN, 4/5/7/8 par SIRET.",
	}
	return []mcp.Outil{
		{
			Nom: "compter",
			Description: "Compte les acheteurs correspondant a un arbre de filtres. " +
				"Approche par defaut et plafonne a 10000, ce qui suffit pour affiner un ciblage " +
				"et repond en quelques secondes ; exact=true rend le compte reel mais peut prendre " +
				"plus d'une minute. C'est l'appel a repeter pour affiner, avant tout echantillon.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":       schemaFiltre(),
				"exact":        map[string]interface{}{"type": "boolean", "default": false},
				"type_blocage": blocage,
			}, "filtre"),
		},
		{
			Nom: "echantillon",
			Description: "Lit les acheteurs correspondant au filtre, page par page. " +
				"Maximum 2000 lignes par appel, 50 par defaut. Pour la page suivante, repasser " +
				"next_cursor dans cursor. Pour recuperer l'integralite d'une selection volumineuse, " +
				"utiliser hellodata_export_csv plutot que de boucler ici. Sans colonnes, rend un " +
				"apercu (id_acheteur, raison_sociale, ville, code_postal) ; si l'utilisateur veut " +
				"d'autres champs, lui montrer la liste de colonnes et le laisser choisir.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":   schemaFiltre(),
				"colonnes": colonnes,
				"taille": map[string]interface{}{
					"type": "integer", "minimum": 1, "maximum": TailleMax, "default": TailleDefaut,
				},
				"cursor":       map[string]interface{}{"type": "integer"},
				"type_blocage": blocage,
			}, "filtre"),
		},
		{
			Nom: "export_csv",
			Description: "AVANT d'appeler cet outil, montrer a l'utilisateur la liste des champs " +
				"disponibles (voir colonnes) et lui demander lesquels extraire ; ne jamais choisir " +
				"les champs a sa place, et dire clairement ceux qui ne sont pas disponibles. " +
				"Rend ensuite le CSV d'une page de la selection, au plus 2000 lignes, sous forme " +
				"d'URL de telechargement. Pour la suite, rappeler avec cursor = next_cursor et les " +
				"memes colonnes. Le lien expire apres 15 minutes.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":       schemaFiltre(),
				"colonnes":     colonnes,
				"cursor":       map[string]interface{}{"type": "integer"},
				"type_blocage": blocage,
			}, "filtre", "colonnes"),
		},
		{
			Nom: "recup_acheteur",
			Description: "Selectionne n acheteurs (1 a 2000) pour une campagne SMS ou appel et les y " +
				"inscrit ; la campagne est creee si son code est inconnu. Les acheteurs sont " +
				"dedoublonnes par numero de telephone. Toujours exclus : ne_plus_contacter, numero " +
				"deja dans cette campagne, numero invalide (ou non mobile en sms). Le filtre combine " +
				"les criteres acheteur et les feuilles d'historique hist_jamais_contacte, " +
				"hist_derniere_categorie, hist_derniere_reponse_il_y_a_plus_de_jours, hist_campagne, " +
				"placees directement sous le ET racine (ou dans un sous-groupe dedie enfant du ET " +
				"racine). Rend les compteurs et url_csv (lien de 15 minutes) a transmettre au " +
				"prestataire. Si epuise=false, rappeler avec la meme campagne pour la suite.",
			SchemaEntre: objet(map[string]interface{}{
				"campagne": objet(map[string]interface{}{
					"code": map[string]interface{}{
						"type": "string", "maxLength": codeMax,
						"description": "Cle de la campagne, a reutiliser pour bilan_campagnes et enregistrer_reponses.",
					},
					"nom":           map[string]interface{}{"type": "string", "maxLength": texteMax},
					"canal":         map[string]interface{}{"type": "string", "enum": []string{"sms", "appel"}},
					"prestataire":   map[string]interface{}{"type": "string", "maxLength": texteMax},
					"message":       map[string]interface{}{"type": "string"},
					"date_campagne": map[string]interface{}{"type": "string", "format": "date"},
				}, "code", "nom", "canal", "date_campagne"),
				"n":      map[string]interface{}{"type": "integer", "minimum": 1, "maximum": NMax},
				"filtre": schemaFiltre(),
			}, "campagne", "n", "filtre"),
		},
		{
			Nom: "bilan_campagnes",
			Description: "Liste les campagnes avec leurs compteurs : envoyes, positive, " +
				"negative_contactable, negative_stop, sans_reponse. Sert a retrouver le code d'une " +
				"campagne. code limite le resultat a une campagne.",
			SchemaEntre: objet(map[string]interface{}{
				"code": map[string]interface{}{"type": "string", "maxLength": codeMax},
			}),
		},
		{
			Nom: "enregistrer_reponses",
			Description: "Enregistre les reponses du prestataire pour une campagne, au plus 500 par " +
				"appel (decouper au-dela). Classer chaque reponse : positive, negative_contactable " +
				"(non, mais d'autres campagnes restent possibles) ou negative_stop (ne veut plus " +
				"rien recevoir : le numero passe en ne_plus_contacter, definitivement). Une reponse " +
				"commencant par STOP est toujours enregistree negative_stop. Rend mis_a_jour, les " +
				"numeros inconnus et ceux hors campagne.",
			SchemaEntre: objet(map[string]interface{}{
				"code_campagne": map[string]interface{}{"type": "string", "maxLength": codeMax},
				"reponses": map[string]interface{}{
					"type": "array", "minItems": 1, "maxItems": ReponsesMax,
					"items": objet(map[string]interface{}{
						"telephone":     map[string]interface{}{"type": "string"},
						"reponse_brute": map[string]interface{}{"type": "string"},
						"categorie": map[string]interface{}{
							"type": "string", "enum": []string{"positive", "negative_contactable", "negative_stop"},
						},
					}, "telephone", "reponse_brute", "categorie"),
				},
			}, "code_campagne", "reponses"),
		},
	}
}
