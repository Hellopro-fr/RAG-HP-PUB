package config

import (
	"os"
	"strings"
)

type Config struct {
	Port    string
	Name    string
	Version string

	// gRPC backend service address
	NormalizationServiceURL string

	// unit-registry-service (unit CRUD); UnitsAdminKey is the Bearer for its write RPCs.
	UnitRegistryAddr string
	UnitsAdminKey    string
	// UnitWriteToolsEnabled exposes the unit/unit-type write tools; off unless explicitly enabled.
	UnitWriteToolsEnabled bool
}

func Load() *Config {
	return &Config{
		Port:    getEnv("MCP_PORT", "8602"),
		Name:    getEnv("MCP_SERVICE_NAME", "mcp-normalize-unite"),
		Version: getEnv("MCP_SERVICE_VERSION", "0.1.0"),

		NormalizationServiceURL: getEnv("NORMALIZATION_SERVICE_URL", "graph-rag-normalize-unite-service:50057"),

		UnitRegistryAddr: getEnv("UNIT_REGISTRY_GRPC_ADDR", "unit-registry-service:50059"),
		UnitsAdminKey:    os.Getenv("UNITS_ADMIN_KEY"),

		UnitWriteToolsEnabled: parseBool(os.Getenv("UNIT_WRITE_TOOLS_ENABLED")),
	}
}

// parseBool is true only for "true", "1" or "yes" (case-insensitive); anything else is false.
func parseBool(v string) bool {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "true", "1", "yes":
		return true
	}
	return false
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
