package config

import "os"

type Config struct {
	Port    string
	Name    string
	Version string

	// gRPC backend service addresses
	EmbeddingServiceURL  string
	DatabaseServiceURL   string
	RerankingServiceURL  string
	LLMServiceURL        string
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8580"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-api-recherche"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		EmbeddingServiceURL: getEnv("EMBEDDING_SERVICE_URL", "embedding-model-service:50052"),
		DatabaseServiceURL:  getEnv("DATABASE_SERVICE_URL", "database-recherche-service:50054"),
		RerankingServiceURL: getEnv("RERANKING_SERVICE_URL", "reranking-model-service:50053"),
		LLMServiceURL:       getEnv("LLM_SERVICE_URL", "llm-service:50051"),
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
