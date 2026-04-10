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
	JWTSecret    string
	JWTAlgo      string
	JWTAudience  string
	AuthURL      string // hellopro.fr auth endpoint
	AuthEnabled  bool   // AUTH_ENABLED — enabled by default, set to "false" to disable login
	SecureCookie bool   // SECURE_COOKIE — set to "true" when behind TLS (default: false for local dev)
	// OAuth2
	GatewayPublicURL      string // GATEWAY_PUBLIC_URL — for metadata issuer and WWW-Authenticate
	OAuth2AccessTokenTTL  int    // OAUTH2_ACCESS_TOKEN_TTL — default access token lifetime in seconds (default 3600)
	OAuth2RefreshTokenTTL int    // OAUTH2_REFRESH_TOKEN_TTL — refresh token lifetime in seconds (default 2592000 = 30 days)
	// URL validation
	AllowInternalURLs bool // ALLOW_INTERNAL_URLS — set to "true" to allow Docker-internal/private IP ranges (e.g. 172.x.x.x)
	// RBAC
	AdminEmails []string // ADMIN_EMAILS — comma-separated emails that get admin role on first login
	// Fallback auth (for users not registered in hellopro.fr)
	FallbackUser  string // FALLBACK_USER
	FallbackPass  string // FALLBACK_PASS
	FallbackEmail string // FALLBACK_EMAIL
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

	oauth2TTL := 3600
	if v := os.Getenv("OAUTH2_ACCESS_TOKEN_TTL"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			oauth2TTL = n
		}
	}

	refreshTTL := 2592000 // 30 days
	if v := os.Getenv("OAUTH2_REFRESH_TOKEN_TTL"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			refreshTTL = n
		}
	}

	// Auth is enabled by default — set AUTH_ENABLED=false to disable
	authEnabled := !strings.EqualFold(os.Getenv("AUTH_ENABLED"), "false")

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
		SecureCookie:        strings.EqualFold(os.Getenv("SECURE_COOKIE"), "true"),
		GatewayPublicURL:      getEnv("GATEWAY_PUBLIC_URL", ""),
		OAuth2AccessTokenTTL:  oauth2TTL,
		OAuth2RefreshTokenTTL: refreshTTL,
		AllowInternalURLs:   strings.EqualFold(os.Getenv("ALLOW_INTERNAL_URLS"), "true"),
		AdminEmails:         parseCSV(os.Getenv("ADMIN_EMAILS")),
		FallbackUser:        os.Getenv("FALLBACK_USER"),
		FallbackPass:        os.Getenv("FALLBACK_PASS"),
		FallbackEmail:       os.Getenv("FALLBACK_EMAIL"),
	}
}

func parseCSV(raw string) []string {
	if raw == "" {
		return nil
	}
	var result []string
	for _, s := range strings.Split(raw, ",") {
		s = strings.TrimSpace(s)
		if s != "" {
			result = append(result, s)
		}
	}
	return result
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
