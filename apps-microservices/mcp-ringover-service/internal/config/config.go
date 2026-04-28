package config

import "os"

type Config struct {
	Port    string
	Name    string
	Version string

	RingoverAPIKey     string
	RingoverAPIBaseURL string

	// AdminToken is the shared secret required on the X-Admin-Token header to
	// reach the non-MCP /admin/* endpoints. When empty, those endpoints are
	// disabled entirely.
	AdminToken string
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8586"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-ringover"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		RingoverAPIKey:     getEnv("RINGOVER_API_KEY", ""),
		RingoverAPIBaseURL: getEnv("RINGOVER_API_BASE_URL", "https://public-api.ringover.com/v2"),

		AdminToken: getEnv("MCP_RINGOVER_ADMIN_TOKEN", ""),
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
