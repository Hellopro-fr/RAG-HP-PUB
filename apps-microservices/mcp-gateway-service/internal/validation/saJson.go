// Package validation — SA JSON validation before encrypt/store.
package validation

import (
	"encoding/json"
	"fmt"
	"strings"
)

const MaxSAJSONSize = 16 * 1024 // 16 KB; real SA JSONs are ~2 KB

type ServiceAccountInfo struct {
	Type        string `json:"type"`
	ProjectID   string `json:"project_id"`
	ClientEmail string `json:"client_email"`
	PrivateKey  string `json:"private_key"`
}

func ValidateServiceAccountJSON(raw []byte) (*ServiceAccountInfo, error) {
	if len(raw) > MaxSAJSONSize {
		return nil, fmt.Errorf("file too large: %d bytes (max %d)", len(raw), MaxSAJSONSize)
	}
	var info ServiceAccountInfo
	if err := json.Unmarshal(raw, &info); err != nil {
		return nil, fmt.Errorf("parse JSON: %w", err)
	}
	if info.Type != "service_account" {
		return nil, fmt.Errorf("type must be service_account, got %q", info.Type)
	}
	if info.ProjectID == "" {
		return nil, fmt.Errorf("project_id is required")
	}
	if info.ClientEmail == "" {
		return nil, fmt.Errorf("client_email is required")
	}
	if !strings.HasSuffix(info.ClientEmail, ".iam.gserviceaccount.com") &&
		!strings.HasSuffix(info.ClientEmail, "@appspot.gserviceaccount.com") {
		return nil, fmt.Errorf("client_email does not look like a service account email")
	}
	if info.PrivateKey == "" {
		return nil, fmt.Errorf("private_key is required")
	}
	if !strings.HasPrefix(strings.TrimSpace(info.PrivateKey), "-----BEGIN PRIVATE KEY-----") {
		return nil, fmt.Errorf("private_key must be PEM-encoded (starts with -----BEGIN PRIVATE KEY-----)")
	}
	return &info, nil
}
