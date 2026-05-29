// Package mcp emits JSON-RPC 2.0 envelopes the service returns when it
// cannot proxy a request (no Zoho configured, misconfigured admin row, etc).
package mcp

import (
	"encoding/json"
)

// rpcError is the standard JSON-RPC error shape.
type rpcError struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

type rpcEnvelope struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      interface{} `json:"id"`
	Error   rpcError    `json:"error"`
}

// WriteRPCError marshals a JSON-RPC error response. id is forwarded from
// the inbound request (number, string, or null). data is attached when non-nil.
func WriteRPCError(id interface{}, code int, message string, data interface{}) []byte {
	env := rpcEnvelope{
		JSONRPC: "2.0",
		ID:      id,
		Error:   rpcError{Code: code, Message: message, Data: data},
	}
	b, _ := json.Marshal(env)
	return b
}

// Codes used by mcp-zoho-service.
const (
	CodeNoZohoConfigured = -32001
	CodeInternalError    = -32603
)
