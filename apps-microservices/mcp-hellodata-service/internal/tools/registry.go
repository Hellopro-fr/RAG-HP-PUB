package tools

import "mcp-hellodata/internal/mcp"

// TailleMax et TailleDefaut bornent la lecture. 2000 est le plafond de la
// spec ; 50 est un echantillon, pas une extraction.
const (
	TailleMax    = 2000
	TailleDefaut = 50
)

// schemaFiltre decrit l'arbre imbrique. La recursion passe par $ref sur
// la definition, ce que les clients MCP savent lire.
func schemaFiltre() map[string]interface{} {
	return map[string]interface{}{
		"$ref": "#/definitions/noeud",
		"definitions": map[string]interface{}{
			"noeud": map[string]interface{}{
				"type":        "object",
				"description": "Soit un groupe {operateur, conditions}, soit une feuille {critere, comparateur, valeur}.",
				"properties": map[string]interface{}{
					"operateur": map[string]interface{}{
						"type": "string", "enum": []string{"ET", "OU", "NON"},
						"description": "NON est unaire : exactement une condition.",
					},
					"conditions": map[string]interface{}{
						"type":     "array",
						"items":    map[string]interface{}{"$ref": "#/definitions/noeud"},
						"minItems": 1, "maxItems": 20,
					},
					"critere":     map[string]interface{}{"type": "string"},
					"comparateur": map[string]interface{}{"type": "string"},
					"valeur":      map[string]interface{}{},
				},
			},
		},
	}
}

func objet(props map[string]interface{}, requis ...string) map[string]interface{} {
	return map[string]interface{}{"type": "object", "properties": props, "required": requis}
}

// Definitions rend les trois outils exposes au LLM. hellodata_export_statut
// n'existe pas : l'export tient sur une seule page, plafonnee a 2000
// lignes, rendue directement par hellodata_export_csv.
//
// Les noms sont SANS le prefixe 'hellodata_' : c'est le gateway qui
// l'ajoute (tool_prefix = "hellodata", PrefixedToolName), comme
// bdd_query_readonly est le prefixe 'bdd' plus l'outil 'query_readonly'.
// Le renommer ici donnerait hellodata_hellodata_compter au LLM.
func Definitions() []mcp.Outil {
	colonnes := map[string]interface{}{
		"type":        "array",
		"items":       map[string]interface{}{"type": "string"},
		"description": "Colonnes a restituer. email et mobile exigent le role admin.",
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
				"utiliser hellodata_export_csv plutot que de boucler ici.",
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
			Description: "Rend le CSV d'une page de la selection, au plus 2000 lignes, sous forme " +
				"d'URL de telechargement. Pour la suite, rappeler avec cursor = next_cursor. " +
				"Le lien expire apres 15 minutes et ne survit pas a un redemarrage du service.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":       schemaFiltre(),
				"colonnes":     colonnes,
				"cursor":       map[string]interface{}{"type": "integer"},
				"type_blocage": blocage,
			}, "filtre"),
		},
	}
}
