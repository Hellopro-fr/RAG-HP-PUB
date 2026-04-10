package tools

import (
	"context"
	"time"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	"github.com/hellopro/mcp-api-recherche/internal/orchestrator"
)

const classicSearchDescription = "Rechercher dans une collection Milvus par filtres uniquement (sans recherche vectorielle ni re-ranking). " +
	"IMPORTANT : avant d'utiliser cet outil, appelez d'abord get_collection_schema pour découvrir les champs disponibles et filtrables, " +
	"puis construisez vos filtres en utilisant uniquement les champs marqués comme filterable. " +
	"Cet outil est idéal pour les requêtes structurées (par ID, catégorie, fournisseur, date, etc.) " +
	"où la similarité sémantique n'est pas nécessaire. " +
	"Collections disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs)."

const classicSearchInputSchema = `{
	"type": "object",
	"properties": {
		"collection": {
			"type": "string",
			"enum": ["produits_3", "siteweb_2", "devis", "echanges", "prix"],
			"description": "Nom de la collection Milvus à interroger"
		},
		"filters": {
			"type": "object",
			"description": "Filtres clé-valeur à appliquer (ex. {\"fournisseur\": \"ACME\", \"categorie\": \"Pompes\"}). Appelez get_collection_schema au préalable pour connaître les champs filtrables."
		},
		"top_k": {
			"type": "integer",
			"description": "Nombre maximum de résultats à retourner",
			"default": 10
		},
		"output_fields": {
			"type": "array",
			"items": { "type": "string" },
			"description": "Champs spécifiques à inclure dans les résultats (obligatoire : appelez get_collection_schema au préalable pour connaître les champs disponibles, puis ne demandez que ceux dont vous avez besoin). Ne pas renseigner ce champ retourne tous les champs, ce qui est déconseillé."
		}
	},
	"required": ["collection", "filters"]
}`

func handleClassicSearch(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	collection, ok := args["collection"].(string)
	if !ok || collection == "" {
		return errorResult("'collection' parameter is required and must be a non-empty string"), nil
	}

	filters, ok := args["filters"].(map[string]any)
	if !ok || len(filters) == 0 {
		return errorResult("'filters' parameter is required and must be a non-empty object"), nil
	}

	topK := 10
	if tk, ok := args["top_k"].(float64); ok {
		topK = int(tk)
	}

	var outputFields []string
	if fields, ok := args["output_fields"].([]any); ok {
		for _, f := range fields {
			if s, ok := f.(string); ok {
				outputFields = append(outputFields, s)
			}
		}
	}

	params := &orchestrator.SearchParams{
		Query:      "",
		TopK:       topK,
		SearchType: "keyword",
		Sources: []orchestrator.SourceFilter{
			{Source: collection, Filters: filters},
		},
		OutputFields: outputFields,
		UseReranker:  false,
	}

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
