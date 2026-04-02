package tools

import (
	"context"
	"fmt"

	"github.com/hellopro/mcp-ringover/internal/mcp"
)

const listContactsDescription = "List all contacts from Ringover"
const listContactsInputSchema = `{
	"type": "object",
	"properties": {}
}`

func handleListContacts(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	data, err := clients.Ringover.GetContacts(ctx)
	if err != nil {
		return nil, fmt.Errorf("GetContacts: %w", err)
	}

	return rawJSONResult(data), nil
}
