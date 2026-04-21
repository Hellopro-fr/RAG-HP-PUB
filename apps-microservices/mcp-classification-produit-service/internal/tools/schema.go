package tools

// -- classify_product ---------------------------------------------------------

const classifyDescription = `Classifier un produit dans le catalogue HelloPro.
Prend en entrée l'identifiant, le nom et la description d'un produit, et retourne
la catégorie la plus pertinente avec un score de confiance.`

const classifyInputSchema = `{
	"type": "object",
	"properties": {
		"id_produit": {
			"type": "string",
			"description": "Identifiant unique du produit (optionnel — auto-généré si absent)"
		},
		"nom_produit": {
			"type": "string",
			"description": "Nom ou titre du produit"
		},
		"description": {
			"type": "string",
			"description": "Description détaillée du produit"
		},
		"id_categorie_attendue": {
			"type": "string",
			"description": "ID de la catégorie attendue (optionnel, pour comparaison)"
		},
		"optimize": {
			"type": "boolean",
			"description": "Optimiser le titre avant la classification (défaut: false)",
			"default": false
		}
	},
	"required": ["nom_produit", "description"]
}`

// -- classify_products_batch --------------------------------------------------

const classifyBatchDescription = `Classifier un lot de produits dans le catalogue HelloPro.
Prend en entrée une liste de produits (max 1200) et retourne les résultats
de classification pour chacun.`

const classifyBatchInputSchema = `{
	"type": "object",
	"properties": {
		"produits": {
			"type": "array",
			"description": "Liste des produits à classifier (max 1200)",
			"items": {
				"type": "object",
				"properties": {
					"id_produit": {
						"type": "string",
						"description": "Identifiant unique du produit (optionnel — auto-généré si absent)"
					},
					"nom_produit": {
						"type": "string",
						"description": "Nom ou titre du produit"
					},
					"description": {
						"type": "string",
						"description": "Description détaillée du produit"
					},
					"id_categorie_attendue": {
						"type": "string",
						"description": "ID de la catégorie attendue (optionnel)"
					}
				},
				"required": ["nom_produit", "description"]
			}
		}
	},
	"required": ["produits"]
}`

// -- list_cached_categories ---------------------------------------------------

const listCachedCategoriesDescription = `Lister tous les résumés de catégories en cache Redis.
Retourne les catégories dont le résumé a été généré et mis en cache
lors de classifications précédentes.`

const listCachedCategoriesInputSchema = `{
	"type": "object",
	"properties": {}
}`

// -- get_cached_category ------------------------------------------------------

const getCachedCategoryDescription = `Obtenir le résumé en cache d'une catégorie spécifique.
Retourne les détails du résumé mis en cache pour la catégorie demandée,
incluant les métriques de temps (scan, récupération, total).`

const getCachedCategoryInputSchema = `{
	"type": "object",
	"properties": {
		"category_id": {
			"type": "string",
			"description": "Identifiant de la catégorie à consulter"
		}
	},
	"required": ["category_id"]
}`
