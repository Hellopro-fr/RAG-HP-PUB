package tools

import (
	"context"
	"time"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	"github.com/hellopro/mcp-api-recherche/internal/orchestrator"
)

const searchDescription = "Search the HelloPro knowledge base across product catalogs, websites, quotes, exchanges, and pricing databases. " +
	"Supports semantic vector search, keyword/filter search, and hybrid search (vector + BM25). " +
	"Results are optionally re-ranked for relevance using a cross-encoder model. " +
	"Returns structured matches grouped by source collection with metadata and relevance scores."

const searchInputSchema = `{
	"type": "object",
	"properties": {
		"query": {
			"type": "string",
			"description": "The search query in natural language (French or English)"
		},
		"sources": {
			"type": "array",
			"description": "Collections to search. Each entry specifies a source name and optional filters. Available sources: produits_3 (products), siteweb_2 (websites), devis (quotes), echanges (conversations), prix (pricing)",
			"items": {
				"type": "object",
				"properties": {
					"source": {
						"type": "string",
						"enum": ["produits_3", "siteweb_2", "devis", "echanges", "prix"]
					},
					"filters": {
						"type": "object",
						"description": "Key-value filters applied to this source (e.g. {\"fournisseur\": \"ACME\"})"
					}
				},
				"required": ["source"]
			},
			"default": [{"source": "produits_3"}]
		},
		"top_k": {
			"type": "integer",
			"description": "Maximum number of results to return per source",
			"default": 10
		},
		"filters": {
			"type": "object",
			"description": "Global filters applied to all sources (e.g. {\"fournisseur\": \"ACME\", \"avec_prix\": true})"
		},
		"output_fields": {
			"type": "array",
			"items": { "type": "string" },
			"description": "Specific fields to include in results. Use get_collection_schema to discover available fields. Empty means all fields."
		},
		"search_type": {
			"type": "string",
			"enum": ["semantic", "keyword", "hybrid"],
			"description": "Search mode: 'semantic' (embedding + vector similarity), 'keyword' (filter-only, no embeddings), 'hybrid' (dense vector + BM25 full-text)",
			"default": "semantic"
		},
		"use_reranker": {
			"type": "boolean",
			"description": "Whether to re-rank results using a cross-encoder model (BAAI/bge-reranker-v2-m3) for improved relevance ordering",
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
