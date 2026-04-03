package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
)

const listUsersDescription = "List all Ringover users"
const listUsersInputSchema = `{
	"type": "object",
	"properties": {}
}`

func handleListUsers(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	data, err := clients.Ringover.GetUsers(ctx)
	if err != nil {
		return nil, fmt.Errorf("GetUsers: %w", err)
	}

	return rawJSONResult(data), nil
}
