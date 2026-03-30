package tools

import (
	"context"
	"time"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	"github.com/hellopro/mcp-api-recherche/internal/orchestrator"
)

const searchDescription = "Rechercher dans la base de connaissances HelloPro à travers les catalogues produits, sites web, devis, échanges et bases de données de prix. " +
	"IMPORTANT : avant d'utiliser cet outil, appelez d'abord get_collection_schema pour découvrir les champs disponibles de chaque collection, " +
	"puis spécifiez uniquement les champs nécessaires via output_fields au lieu de récupérer tous les champs. " +
	"Supporte la recherche sémantique vectorielle, la recherche par mots-clés/filtres, et la recherche hybride (vecteur + BM25). " +
	"Les résultats sont optionnellement re-classés par pertinence à l'aide d'un modèle cross-encoder. " +
	"Retourne des correspondances structurées regroupées par collection source avec métadonnées et scores de pertinence."

const searchInputSchema = `{
	"type": "object",
	"properties": {
		"query": {
			"type": "string",
			"description": "La requête de recherche en langage naturel (français ou anglais)"
		},
		"sources": {
			"type": "array",
			"description": "Collections à rechercher. Chaque entrée spécifie un nom de source et des filtres optionnels. Sources disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs)",
			"items": {
				"type": "object",
				"properties": {
					"source": {
						"type": "string",
						"enum": ["produits_3", "siteweb_2", "devis", "echanges", "prix"]
					},
					"filters": {
						"type": "object",
						"description": "Filtres clé-valeur appliqués à cette source (ex. {\"fournisseur\": \"ACME\"})"
					}
				},
				"required": ["source"]
			},
			"default": [{"source": "produits_3"}]
		},
		"top_k": {
			"type": "integer",
			"description": "Nombre maximum de résultats à retourner par source",
			"default": 10
		},
		"filters": {
			"type": "object",
			"description": "Filtres globaux appliqués à toutes les sources (ex. {\"fournisseur\": \"ACME\", \"avec_prix\": true})"
		},
		"output_fields": {
			"type": "array",
			"items": { "type": "string" },
			"description": "Champs spécifiques à inclure dans les résultats (obligatoire : appelez get_collection_schema au préalable pour connaître les champs disponibles, puis ne demandez que ceux dont vous avez besoin). Ne pas renseigner ce champ retourne tous les champs, ce qui est déconseillé."
		},
		"search_type": {
			"type": "string",
			"enum": ["semantic", "keyword", "hybrid"],
			"description": "Mode de recherche : 'semantic' (embedding + similarité vectorielle), 'keyword' (filtres uniquement, sans embeddings), 'hybrid' (vecteur dense + BM25 plein texte)",
			"default": "semantic"
		},
		"use_reranker": {
			"type": "boolean",
			"description": "Indique s'il faut re-classer les résultats à l'aide d'un modèle cross-encoder (BAAI/bge-reranker-v2-m3) pour un meilleur classement par pertinence",
			"default": true
		}
	},
	"required": ["query"]
}`

// searchOrchestrator is set during registry initialization.
var searchOrchestrator *orchestrator.SearchOrchestrator

// SetSearchOrchestrator sets the orchestrator used by the search tool.
func SetSearchOrchestrator(o *orchestrator.SearchOrchestrator) {
	searchOrchestrator = o
}

func handleSearch(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	query, ok := args["query"].(string)
	if !ok || query == "" {
		return errorResult("'query' parameter is required and must be a non-empty string"), nil
	}

	params := &orchestrator.SearchParams{
		Query:       query,
		TopK:        10,
		SearchType:  "semantic",
		UseReranker: true,
	}

	// Parse sources
	if rawSources, ok := args["sources"].([]any); ok {
		for _, rs := range rawSources {
			if sm, ok := rs.(map[string]any); ok {
				sf := orchestrator.SourceFilter{
					Source: "produits_3",
				}
				if s, ok := sm["source"].(string); ok {
					sf.Source = s
				}
				if f, ok := sm["filters"].(map[string]any); ok {
					sf.Filters = f
				}
				params.Sources = append(params.Sources, sf)
			}
		}
	}

	if topK, ok := args["top_k"].(float64); ok {
		params.TopK = int(topK)
	}

	if filters, ok := args["filters"].(map[string]any); ok {
		params.Filters = filters
	}

	if fields, ok := args["output_fields"].([]any); ok {
		for _, f := range fields {
			if s, ok := f.(string); ok {
				params.OutputFields = append(params.OutputFields, s)
			}
		}
	}

	if st, ok := args["search_type"].(string); ok {
		params.SearchType = st
	}

	if reranker, ok := args["use_reranker"].(bool); ok {
		params.UseReranker = reranker
	}

	// Add timeout for the search operation
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	if searchOrchestrator == nil {
		return errorResult("search orchestrator not initialized"), nil
	}

	result, err := searchOrchestrator.Search(ctx, params)
	if err != nil {
		return errorResult(err.Error()), nil
	}

	return jsonResult(result), nil
}
