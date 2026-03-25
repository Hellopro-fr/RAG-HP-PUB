package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-api-recherche/internal/mcp"
	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
)

const schemaDescription = "Retrieve the schema (field names and types) of a Milvus collection. " +
	"Use this to discover which fields are available for filtering and what output_fields can be requested in a search. " +
	"Available collections: produits_3 (products), siteweb_2 (websites), devis (quotes), echanges (conversations), prix (pricing)."

const schemaInputSchema = `{
	"type": "object",
	"properties": {
		"collection": {
			"type": "string",
			"description": "Name of the Milvus collection (e.g. produits_3, siteweb_2, devis, echanges, prix)"
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
