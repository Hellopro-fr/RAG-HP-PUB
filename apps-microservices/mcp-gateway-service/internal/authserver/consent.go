package authserver

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

// ConsentScope represents the scope granted during consent.
type ConsentScope struct {
	ServerIDs   []string             `json:"server_ids"`
	ServerTools []ServerToolSelection `json:"server_tools,omitempty"`
}

// ServerToolSelection represents tools selected for a specific server.
type ServerToolSelection struct {
	ServerID  string   `json:"server_id"`
	ToolNames []string `json:"tool_names"`
}

func (s ConsentScope) ToJSON() string {
	b, _ := json.Marshal(s)
	return string(b)
}

func ParseConsentScope(j string) (*ConsentScope, error) {
	var scope ConsentScope
	if err := json.Unmarshal([]byte(j), &scope); err != nil {
		return nil, fmt.Errorf("parse consent scope: %w", err)
	}
	return &scope, nil
}

func generateCSRFToken() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
