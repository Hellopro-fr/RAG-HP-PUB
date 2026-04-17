package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-classification-produit/internal/mcp"
)

// handleClassifyProduct classifies a single product via the classification API.
// id_produit is optional: if missing or empty, a synthetic "auto-<hex>" value
// is generated at the MCP layer so the backend contract is preserved.
func handleClassifyProduct(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	idProduit, _ := args["id_produit"].(string)
	nomProduit, _ := args["nom_produit"].(string)
	description, _ := args["description"].(string)

	if nomProduit == "" || description == "" {
		return errorResult("nom_produit and description are required"), nil
	}

	if idProduit == "" {
		idProduit = generateAutoID()
	}

	payload := map[string]any{
		"id_produit":  idProduit,
		"nom_produit": nomProduit,
		"description": description,
	}

	if v, ok := args["id_categorie_attendue"].(string); ok && v != "" {
		payload["id_categorie_attendue"] = v
	}
	if v, ok := args["optimize"].(bool); ok {
		payload["optimize"] = v
	}

	body, err := doPost(ctx, clients, "/classification/classify", payload)
	if err != nil {
		return nil, fmt.Errorf("classify_product: %w", err)
	}

	return textResult(string(body)), nil
}

// handleClassifyProductsBatch classifies a batch of products via the classification API.
func handleClassifyProductsBatch(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	produits, ok := args["produits"]
	if !ok {
		return errorResult("produits is required"), nil
	}

	// Validate that produits is an array
	produitsSlice, ok := produits.([]any)
	if !ok || len(produitsSlice) == 0 {
		return errorResult("produits must be a non-empty array"), nil
	}

	payload := map[string]any{
		"produits": produits,
	}

	body, err := doPost(ctx, clients, "/classification/classify/batch", payload)
	if err != nil {
		return nil, fmt.Errorf("classify_products_batch: %w", err)
	}

	return textResult(string(body)), nil
}
