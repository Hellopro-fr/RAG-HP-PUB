package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Port                string
	Name                string
	Version             string
	BackendServers      []string // backward compat: MCP_BACKEND_SERVERS env var
	MySQLDSN            string
	EncryptionKey       string // hex-encoded 32-byte key for AES-256-GCM
	HealthCheckInterval int    // seconds between health checks (default 30)
	// Auth
	JWTSecret   string
	JWTAlgo     string
	JWTAudience string
	AuthURL     string // hellopro.fr auth endpoint
	AuthEnabled bool   // set AUTH_ENABLED=true to require login
}

func Load() *Config {
	port := getEnv("MCP_GATEWAY_PORT", "8560")
	name := getEnv("MCP_GATEWAY_NAME", "hellopro-mcp-gateway")
	version := getEnv("MCP_GATEWAY_VERSION", "0.1.0")

	var backends []string
	if raw := os.Getenv("MCP_BACKEND_SERVERS"); raw != "" {
		for _, s := range strings.Split(raw, ",") {
			s = strings.TrimSpace(s)
			if s != "" {
				backends = append(backends, s)
			}
		}
	}

	healthInterval := 30
	if v := os.Getenv("HEALTH_CHECK_INTERVAL"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			healthInterval = n
		}
	}

	authEnabled := strings.EqualFold(os.Getenv("AUTH_ENABLED"), "true")

	return &Config{
		Port:                port,
		Name:                name,
		Version:             version,
		BackendServers:      backends,
		MySQLDSN:            os.Getenv("MYSQL_DSN"),
		EncryptionKey:       os.Getenv("ENCRYPTION_KEY"),
		HealthCheckInterval: healthInterval,
		JWTSecret:           getEnv("JWT_SECRET", ""),
		JWTAlgo:             getEnv("JWT_ALGO", "HS256"),
		JWTAudience:         getEnv("JWT_AUDIENCE", "https://www.hellopro.fr"),
		AuthURL:             getEnv("AUTH_URL", "https://www.hellopro.fr/partenaires_externes/info_produit/auth/auth.php"),
		AuthEnabled:         authEnabled,
	}
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
