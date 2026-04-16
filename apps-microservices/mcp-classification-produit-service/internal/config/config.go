package config

import "os"

type Config struct {
	Port    string
	Name    string
	Version string

	// HTTP backend service address
	ClassificationAPIURL string
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8591"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-classification-produit"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		ClassificationAPIURL: getEnv("CLASSIFICATION_API_URL", "http://api-classification-service:8577"),
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
