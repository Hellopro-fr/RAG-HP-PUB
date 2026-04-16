package tools

import (
	"context"
	"fmt"
	"net/url"

	"github.com/hellopro/mcp-classification-produit/internal/mcp"
)

// handleListCachedCategories retrieves all cached category summaries from Redis.
func handleListCachedCategories(ctx context.Context, clients *Clients, _ map[string]any) (*mcp.CallToolResult, error) {
	body, err := doGet(ctx, clients, "/classification/cache/categories")
	if err != nil {
		return nil, fmt.Errorf("list_cached_categories: %w", err)
	}

	return textResult(string(body)), nil
}

// handleGetCachedCategory retrieves the cached summary for a specific category.
func handleGetCachedCategory(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	categoryID, _ := args["category_id"].(string)
	if categoryID == "" {
		return errorResult("category_id is required"), nil
	}

	path := "/classification/cache/categories/" + url.PathEscape(categoryID)
	body, err := doGet(ctx, clients, path)
	if err != nil {
		return nil, fmt.Errorf("get_cached_category: %w", err)
	}

	return textResult(string(body)), nil
}
