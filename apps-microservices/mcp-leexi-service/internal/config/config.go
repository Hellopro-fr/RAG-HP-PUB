package config

import "os"

type Config struct {
	Port    string
	Name    string
	Version string

	LeexiAPIKeyID     string
	LeexiAPIKeySecret string
	LeexiAPIBaseURL   string
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8589"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-leexi"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		LeexiAPIKeyID:     getEnv("LEEXI_API_KEY_ID", ""),
		LeexiAPIKeySecret: getEnv("LEEXI_API_KEY_SECRET", ""),
		LeexiAPIBaseURL:   getEnv("LEEXI_API_BASE_URL", "https://public-api.leexi.ai/v1"),
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
