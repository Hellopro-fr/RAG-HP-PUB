package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	embeddingpb "github.com/hellopro/mcp-api-recherche/proto/gen/embedding"
)

const embedDescription = "Convertir du texte en vecteurs d'embedding de 1024 dimensions à l'aide du modèle CamemBERT-large. " +
	"Utile pour calculer la similarité entre des textes ou pour des flux de recherche personnalisés. " +
	"Supporte le traitement par lots de plusieurs textes."

const embedInputSchema = `{
	"type": "object",
	"properties": {
		"texts": {
			"type": "array",
			"items": { "type": "string" },
			"description": "Liste de textes à convertir en embeddings (traitement par lots supporté)"
		}
	},
	"required": ["texts"]
}`

func handleEmbedText(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	rawTexts, ok := args["texts"]
	if !ok {
		return errorResult("'texts' parameter is required"), nil
	}

	textsSlice, ok := rawTexts.([]any)
	if !ok {
		return errorResult("'texts' must be an array of strings"), nil
	}

	texts := make([]string, 0, len(textsSlice))
	for _, t := range textsSlice {
		s, ok := t.(string)
		if !ok {
			return errorResult("each element in 'texts' must be a string"), nil
		}
		texts = append(texts, s)
	}

	if len(texts) == 0 {
		return errorResult("'texts' must contain at least one text"), nil
	}

	resp, err := clients.Embedding.GetEmbeddings(ctx, &embeddingpb.EmbeddingsRequest{
		Texts:         texts,
		SourceService: strPtr("mcp-api-recherche"),
	})
	if err != nil {
		return nil, fmt.Errorf("GetEmbeddings gRPC call failed: %w", err)
	}

	type embeddingResult struct {
		Text      string    `json:"text"`
		Vector    []float32 `json:"vector"`
		Dimension int       `json:"dimension"`
	}

	results := make([]embeddingResult, 0, len(resp.GetEmbeddings()))
	for i, emb := range resp.GetEmbeddings() {
		vec := emb.GetVector()
		text := ""
		if i < len(texts) {
			text = texts[i]
		}
		results = append(results, embeddingResult{
			Text:      text,
			Vector:    vec,
			Dimension: len(vec),
		})
	}

	return jsonResult(results), nil
}
