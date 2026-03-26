package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	rerankingpb "github.com/hellopro/mcp-api-recherche/proto/gen/reranking"
)

const rerankDescription = "Re-rank a list of text documents by relevance to a query using a cross-encoder model (BAAI/bge-reranker-v2-m3). " +
	"Returns documents sorted by relevance with scores. " +
	"Useful when you have search results and want to re-order them by relevance to a refined query."

const rerankInputSchema = `{
	"type": "object",
	"properties": {
		"query": {
			"type": "string",
			"description": "The query to rank documents against"
		},
		"documents": {
			"type": "array",
			"items": { "type": "string" },
			"description": "List of text documents to re-rank"
		}
	},
	"required": ["query", "documents"]
}`

func handleRerank(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	query, ok := args["query"].(string)
	if !ok || query == "" {
		return errorResult("'query' parameter is required and must be a string"), nil
	}

	rawDocs, ok := args["documents"]
	if !ok {
		return errorResult("'documents' parameter is required"), nil
	}

	docsSlice, ok := rawDocs.([]any)
	if !ok {
		return errorResult("'documents' must be an array of strings"), nil
	}

	documents := make([]string, 0, len(docsSlice))
	for _, d := range docsSlice {
		s, ok := d.(string)
		if !ok {
			return errorResult("each element in 'documents' must be a string"), nil
		}
		documents = append(documents, s)
	}

	if len(documents) == 0 {
		return errorResult("'documents' must contain at least one document"), nil
	}

	resp, err := clients.Reranking.RerankDocuments(ctx, &rerankingpb.RerankRequest{
		Query:     query,
		Documents: documents,
	})
	if err != nil {
		return nil, fmt.Errorf("RerankDocuments gRPC call failed: %w", err)
	}

	type scoredDoc struct {
		Document string  `json:"document"`
		Score    float32 `json:"score"`
		Rank     int     `json:"rank"`
	}

	results := make([]scoredDoc, 0, len(resp.GetScores()))
	for i, s := range resp.GetScores() {
		results = append(results, scoredDoc{
			Document: s.GetDocument(),
			Score:    s.GetScore(),
			Rank:     i + 1,
		})
	}

	return jsonResult(map[string]any{
		"query":   query,
		"results": results,
	}), nil
}
