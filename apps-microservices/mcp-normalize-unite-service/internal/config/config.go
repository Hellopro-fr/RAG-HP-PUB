package config

import "os"

type Config struct {
	Port    string
	Name    string
	Version string

	// gRPC backend service address
	NormalizationServiceURL string
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8602"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-normalize-unite"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		NormalizationServiceURL: getEnv("NORMALIZATION_SERVICE_URL", "graph-rag-normalize-unite-service:50057"),
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
