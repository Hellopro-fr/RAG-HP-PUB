package orchestrator

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sort"
	"sync"
	"time"

	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
	embeddingpb "github.com/hellopro/mcp-api-recherche/proto/gen/embedding"
	rerankingpb "github.com/hellopro/mcp-api-recherche/proto/gen/reranking"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/structpb"
)

// SearchParams holds parsed parameters for a search operation.
type SearchParams struct {
	Query        string
	Sources      []SourceFilter
	TopK         int
	Filters      map[string]any
	OutputFields []string
	SearchType   string // "semantic", "keyword", "hybrid"
	UseReranker  bool
}

// SourceFilter represents a source collection with optional filters.
type SourceFilter struct {
	Source  string         `json:"source"`
	Filters map[string]any `json:"filters,omitempty"`
}

// SearchResult holds the result of a search operation.
type SearchResult struct {
	Query       string                       `json:"query"`
	SearchType  string                       `json:"search_type"`
	Matches     map[string][]map[string]any  `json:"matches"`
	Timings     SearchTimings                `json:"timings"`
	TotalCount  int                          `json:"total_count"`
}

// SearchTimings contains performance metrics.
type SearchTimings struct {
	EmbeddingMs    float64 `json:"embedding_ms"`
	SearchMs       float64 `json:"search_ms"`
	RerankMs       float64 `json:"rerank_ms"`
	TotalMs        float64 `json:"total_ms"`
}

// SearchOrchestrator coordinates the search pipeline.
type SearchOrchestrator struct {
	embeddingClient embeddingpb.EmbeddingServiceClient
	databaseClient  databasepb.DatabaseSearchServiceClient
	rerankingClient rerankingpb.RerankingServiceClient
	filterBuilder   *FilterBuilder
	embeddingCache  *EmbeddingCache
}

func NewSearchOrchestrator(
	embedding embeddingpb.EmbeddingServiceClient,
	database databasepb.DatabaseSearchServiceClient,
	reranking rerankingpb.RerankingServiceClient,
	filterBuilder *FilterBuilder,
) *SearchOrchestrator {
	return &SearchOrchestrator{
		embeddingClient: embedding,
		databaseClient:  database,
		rerankingClient: reranking,
		filterBuilder:   filterBuilder,
		embeddingCache:  NewEmbeddingCache(1000, 1*time.Hour),
	}
}

// Search executes the full search pipeline.
func (so *SearchOrchestrator) Search(ctx context.Context, params *SearchParams) (*SearchResult, error) {
	startTotal := time.Now()
	var embedDuration, searchDuration, rerankDuration time.Duration

	// Default values
	if params.TopK <= 0 {
		params.TopK = 10
	}
	if params.SearchType == "" {
		params.SearchType = "semantic"
	}
	if len(params.Sources) == 0 {
		params.Sources = []SourceFilter{{Source: "produits_3"}}
	}

	topKRetrieval := params.TopK
	if params.UseReranker {
		topKRetrieval = int(float64(params.TopK) * 1.1)
		if topKRetrieval == params.TopK {
			topKRetrieval = params.TopK + 1
		}
	}

	// Step 1: Get embedding (if not keyword search) — with cache
	var queryVector []float32
	if params.SearchType != "keyword" {
		startEmbed := time.Now()

		// Check cache first
		if cached := so.embeddingCache.Get(params.Query); cached != nil {
			queryVector = cached
			embedDuration = time.Since(startEmbed)
			log.Printf("[search] embedding cache hit for query (%.1fms)", float64(embedDuration.Microseconds())/1000)
		} else {
			resp, err := so.embeddingClient.GetEmbeddings(ctx, &embeddingpb.EmbeddingsRequest{
				Texts:         []string{params.Query},
				SourceService: strPtr("mcp-api-recherche"),
			})
			if err != nil {
				return nil, fmt.Errorf("embedding failed: %w", err)
			}
			embeddings := resp.GetEmbeddings()
			if len(embeddings) == 0 || len(embeddings[0].GetVector()) == 0 {
				return nil, fmt.Errorf("empty embedding response")
			}
			queryVector = embeddings[0].GetVector()
			embedDuration = time.Since(startEmbed)
			log.Printf("[search] embedding cache miss (%.0fms), caching result", float64(embedDuration.Milliseconds()))

			// Store in cache
			so.embeddingCache.Set(params.Query, queryVector)
		}
	}

	// Step 2: Search each source in parallel
	startSearch := time.Now()
	allResults := make(map[string][]map[string]any)
	var mu sync.Mutex
	var wg sync.WaitGroup
	errs := make([]error, 0)

	for _, src := range params.Sources {
		wg.Add(1)
		go func(sf SourceFilter) {
			defer wg.Done()

			// Merge global filters with source-specific filters
			mergedFilters := mergeFilters(params.Filters, sf.Filters)

			filterExpr, err := so.filterBuilder.Build(ctx, mergedFilters, sf.Source)
			if err != nil {
				log.Printf("[search] filter build error for %s: %v", sf.Source, err)
			}

			// Auto-upgrade semantic to hybrid if collection supports sparse embeddings
			searchType := params.SearchType
			if searchType == "semantic" && so.collectionSupportsHybrid(ctx, sf.Source) {
				searchType = "hybrid"
				log.Printf("[search] auto-upgraded to hybrid search for %s (sparse_embedding detected)", sf.Source)
			}

			results, err := so.executeSearch(ctx, sf.Source, queryVector, params.Query,
				topKRetrieval, filterExpr, params.OutputFields, searchType)
			if err != nil {
				log.Printf("[search] search error for %s: %v", sf.Source, err)
				mu.Lock()
				errs = append(errs, fmt.Errorf("%s: %w", sf.Source, err))
				mu.Unlock()
				return
			}

			mu.Lock()
			allResults[sf.Source] = results
			mu.Unlock()
		}(src)
	}
	wg.Wait()
	searchDuration = time.Since(startSearch)

	if len(allResults) == 0 && len(errs) > 0 {
		return nil, fmt.Errorf("all searches failed: %v", errs)
	}

	// Step 3: Rerank results (if enabled)
	if params.UseReranker {
		startRerank := time.Now()
		for source, matches := range allResults {
			if len(matches) == 0 {
				continue
			}

			docs := make([]string, 0, len(matches))
			for _, m := range matches {
				text := extractText(m)
				docs = append(docs, text)
			}

			resp, err := so.rerankingClient.RerankDocuments(ctx, &rerankingpb.RerankRequest{
				Query:     params.Query,
				Documents: docs,
			})
			if err != nil {
				log.Printf("[search] reranking failed for %s, keeping original order: %v", source, err)
				allResults[source] = truncate(matches, params.TopK)
				continue
			}

			// Build a map from text to match for reordering
			textToMatch := make(map[string]map[string]any)
			for _, m := range matches {
				textToMatch[extractText(m)] = m
			}

			reranked := make([]map[string]any, 0, len(resp.GetScores()))
			for _, score := range resp.GetScores() {
				if m, ok := textToMatch[score.GetDocument()]; ok {
					m["reranking_score"] = score.GetScore()
					reranked = append(reranked, m)
				}
			}
			allResults[source] = truncate(reranked, params.TopK)
		}
		rerankDuration = time.Since(startRerank)
	} else {
		// Sort by score and truncate
		for source, matches := range allResults {
			sort.Slice(matches, func(i, j int) bool {
				si, _ := matches[i]["score"].(float64)
				sj, _ := matches[j]["score"].(float64)
				return si > sj
			})
			allResults[source] = truncate(matches, params.TopK)
		}
	}

	totalDuration := time.Since(startTotal)

	totalCount := 0
	for _, matches := range allResults {
		totalCount += len(matches)
	}

	return &SearchResult{
		Query:      params.Query,
		SearchType: params.SearchType,
		Matches:    allResults,
		Timings: SearchTimings{
			EmbeddingMs: float64(embedDuration.Milliseconds()),
			SearchMs:    float64(searchDuration.Milliseconds()),
			RerankMs:    float64(rerankDuration.Milliseconds()),
			TotalMs:     float64(totalDuration.Milliseconds()),
		},
		TotalCount: totalCount,
	}, nil
}

func (so *SearchOrchestrator) executeSearch(
	ctx context.Context,
	collection string,
	queryVector []float32,
	queryText string,
	topK int,
	filterExpr string,
	outputFields []string,
	searchType string,
) ([]map[string]any, error) {
	var resp *databasepb.SearchResponse
	var err error

	switch searchType {
	case "keyword":
		req := &databasepb.ClassicSearchRequest{
			CollectionName:   collection,
			FilterExpression: filterExpr,
			TopK:             int32(topK),
			OutputFields:     outputFields,
			SourceService:    strPtr("mcp-api-recherche"),
		}
		resp, err = so.databaseClient.ClassicSearch(ctx, req)

	case "hybrid":
		denseWeight := float32(0.7)
		sparseWeight := float32(0.3)
		// Use RRF (Reciprocal Rank Fusion) — robust to score-scale differences
		// between dense COSINE and sparse BM25. dense_weight/sparse_weight are
		// kept for backward compatibility but ignored when ranker_type=rrf.
		const rankerType = "rrf"
		const rrfK = 60
		options, optErr := structpb.NewStruct(map[string]any{
			"rankerType": rankerType,
			"rrfK":       float64(rrfK),
		})
		if optErr != nil {
			return nil, fmt.Errorf("build hybrid options: %w", optErr)
		}
		log.Printf("[search] hybrid request for %s: ranker_type=%s, rrf_k=%d, dense_weight=%.2f, sparse_weight=%.2f",
			collection, rankerType, rrfK, denseWeight, sparseWeight)
		req := &databasepb.HybridSearchRequest{
			CollectionName:  collection,
			DenseVector:     queryVector,
			QueryText:       queryText,
			TopK:            int32(topK),
			DenseWeight:     &denseWeight,
			SparseWeight:    &sparseWeight,
			OutputFields:    outputFields,
			SourceService:   strPtr("mcp-api-recherche"),
			Options:         options,
		}
		if filterExpr != "" {
			req.FilterExpression = &filterExpr
		}
		resp, err = so.databaseClient.HybridSearch(ctx, req)

	default: // "semantic"
		req := &databasepb.SearchRequest{
			CollectionName: collection,
			QueryEmbedding: queryVector,
			TopK:           int32(topK),
			OutputFields:   outputFields,
			SourceService:  strPtr("mcp-api-recherche"),
		}
		if filterExpr != "" {
			req.FilterExpression = &filterExpr
		}
		resp, err = so.databaseClient.Search(ctx, req)
	}

	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(resp.GetResults()))
	for _, r := range resp.GetResults() {
		entry := map[string]any{
			"id":     r.GetId(),
			"score":  r.GetScore(),
			"source": r.GetSource(),
		}

		// Convert protobuf Struct metadata to map
		if r.GetMetadata() != nil {
			jsonBytes, err := protojson.Marshal(r.GetMetadata())
			if err == nil {
				var meta map[string]any
				if json.Unmarshal(jsonBytes, &meta) == nil {
					entry["metadata"] = meta
				}
			}
		}

		results = append(results, entry)
	}

	return results, nil
}

func extractText(match map[string]any) string {
	if meta, ok := match["metadata"].(map[string]any); ok {
		if entity, ok := meta["entity"].(map[string]any); ok {
			if text, ok := entity["text"].(string); ok {
				return text
			}
		}
		// Fallback: try direct text field
		if text, ok := meta["text"].(string); ok {
			return text
		}
	}
	// Last resort: marshal the whole match
	b, _ := json.Marshal(match)
	return string(b)
}

func truncate(matches []map[string]any, topK int) []map[string]any {
	if len(matches) <= topK {
		return matches
	}
	return matches[:topK]
}

// collectionSupportsHybrid checks if a collection has a sparse_embedding field,
// which indicates it supports hybrid (dense + BM25) search.
func (so *SearchOrchestrator) collectionSupportsHybrid(ctx context.Context, collection string) bool {
	fields, err := so.filterBuilder.GetFieldTypes(ctx, collection)
	if err != nil || len(fields) == 0 {
		return false
	}
	_, hasSparse := fields["sparse_embedding"]
	return hasSparse
}

func mergeFilters(global, source map[string]any) map[string]any {
	if len(global) == 0 && len(source) == 0 {
		return nil
	}
	merged := make(map[string]any)
	for k, v := range global {
		merged[k] = v
	}
	for k, v := range source {
		merged[k] = v
	}
	return merged
}
