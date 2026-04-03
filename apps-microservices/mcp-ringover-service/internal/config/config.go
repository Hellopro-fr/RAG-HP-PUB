package config

import "os"

type Config struct {
	Port    string
	Name    string
	Version string

	RingoverAPIKey     string
	RingoverAPIBaseURL string
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8586"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-ringover"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		RingoverAPIKey:     getEnv("RINGOVER_API_KEY", ""),
		RingoverAPIBaseURL: getEnv("RINGOVER_API_BASE_URL", "https://public-api.ringover.com/v2"),
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
