package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
)

const schemaDescription = "Récupérer le schéma (noms et types des champs) d'une collection Milvus. " +
	"Utilisez cet outil pour découvrir les champs disponibles pour le filtrage et les output_fields pouvant être demandés lors d'une recherche. " +
	"Collections disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs)."

const schemaInputSchema = `{
	"type": "object",
	"properties": {
		"collection": {
			"type": "string",
			"description": "Nom de la collection Milvus (ex. produits_3, siteweb_2, devis, echanges, prix)"
		}
	},
	"required": ["collection"]
}`

func handleGetCollectionSchema(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	collection, ok := args["collection"].(string)
	if !ok || collection == "" {
		return errorResult("'collection' parameter is required and must be a string"), nil
	}

	resp, err := clients.Database.GetSchema(ctx, &databasepb.GetSchemaRequest{
		CollectionName: collection,
		SourceService:  strPtr("mcp-api-recherche"),
	})
	if err != nil {
		return nil, fmt.Errorf("GetSchema gRPC call failed: %w", err)
	}

	result := map[string]any{
		"collection": collection,
		"fields":     resp.GetFields(),
	}
	return jsonResult(result), nil
}

func strPtr(s string) *string {
	return &s
}
