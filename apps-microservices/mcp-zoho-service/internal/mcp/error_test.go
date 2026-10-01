package mcp

import (
	"encoding/json"
	"testing"
)

func TestWriteRPCError(t *testing.T) {
	body := WriteRPCError(42, -32001, "no_zoho_configured", map[string]string{"end_user_email": "alice@hp.fr"})

	var out struct {
		JSONRPC string `json:"jsonrpc"`
		ID      int    `json:"id"`
		Error   struct {
			Code    int                    `json:"code"`
			Message string                 `json:"message"`
			Data    map[string]interface{} `json:"data"`
		} `json:"error"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	if out.JSONRPC != "2.0" {
		t.Fatalf("jsonrpc = %q", out.JSONRPC)
	}
	if out.Error.Code != -32001 || out.Error.Message != "no_zoho_configured" {
		t.Fatalf("error envelope = %+v", out.Error)
	}
	if out.Error.Data["end_user_email"] != "alice@hp.fr" {
		t.Fatalf("error.data = %+v", out.Error.Data)
	}
}
