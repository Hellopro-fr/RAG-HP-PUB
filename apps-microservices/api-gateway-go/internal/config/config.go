package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all runtime configuration loaded from environment variables.
type Config struct {
	JWTSecret                string
	JWTAlgo                  string
	JWTAudience              string
	GatewayAdminKey          string
	AccessTokenExpireMinutes int

	MySQLHost string
	MySQLPort string
	MySQLUser string
	MySQLPass string
	MySQLDB   string

	RedisURL string

	AccountBaseURL     string
	AccountPublicURL   string
	AccountRedirectURI string

	SecureCookie    bool
	ServiceName     string
	DocsAdminEmails []string

	UseCatalog             bool
	APICatalogGRPC         string
	CatalogRefreshInterval time.Duration
	CatalogDialTimeout     time.Duration
}

// Load reads environment variables and returns a populated Config.
// Missing optional variables fall back to safe defaults.
func Load() Config {
	accountBase := strings.TrimRight(getenv("ACCOUNT_BASE_URL", "http://account-service-backend:8600"), "/")

	cfg := Config{
		JWTSecret:                os.Getenv("JWT_SECRET"),
		JWTAlgo:                  getenv("JWT_ALGO", "HS256"),
		JWTAudience:              getenv("JWT_AUDIENCE", "hellopro"),
		GatewayAdminKey:          os.Getenv("GATEWAY_ADMIN_KEY"),
		AccessTokenExpireMinutes: getenvInt("ACCESS_TOKEN_EXPIRE_MINUTES", 15),

		MySQLHost: getenv("MYSQL_HOST", "gateway-mysql"),
		MySQLPort: getenv("MYSQL_PORT", "3306"),
		MySQLUser: getenv("MYSQL_USER", "gateway_user"),
		MySQLPass: getenv("MYSQL_PASS", "gateway_pass"),
		MySQLDB:   getenv("MYSQL_DB", "gateway_db"),

		RedisURL: os.Getenv("REDIS_URL"),

		AccountBaseURL:     accountBase,
		AccountPublicURL:   strings.TrimRight(getenv("ACCOUNT_PUBLIC_URL", accountBase), "/"),
		AccountRedirectURI: os.Getenv("ACCOUNT_REDIRECT_URI"),

		SecureCookie:    getenvBool("SECURE_COOKIE", false),
		ServiceName:     getenv("SERVICE_NAME", "api-gateway"),
		DocsAdminEmails: parseAdminEmails(os.Getenv("GATEWAY_DOCS_ADMIN_EMAILS")),

		UseCatalog:             getenvBool("GATEWAY_USE_CATALOG", false),
		APICatalogGRPC:         getenv("API_CATALOG_GRPC", "api-catalog-service:9100"),
		CatalogRefreshInterval: getenvDuration("CATALOG_REFRESH_INTERVAL", 60*time.Second),
		CatalogDialTimeout:     getenvDuration("CATALOG_DIAL_TIMEOUT", 3*time.Second),
	}

	return cfg
}

// getenv returns the env var value or def when the var is unset or empty.
func getenv(key, def string) string {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return def
	}
	return v
}

// getenvInt parses an integer env var, returning def on parse failure or absence.
func getenvInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

// getenvBool parses a boolean env var ("1", "true", "yes" → true).
func getenvBool(key string, def bool) bool {
	v := strings.ToLower(os.Getenv(key))
	if v == "" {
		return def
	}
	return v == "1" || v == "true" || v == "yes"
}

// getenvDuration parses a duration env var (e.g. "30s", "5m"), returning def on absence or parse failure.
func getenvDuration(key string, def time.Duration) time.Duration {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return def
	}
	return d
}

// parseAdminEmails splits a comma-separated email list, trims whitespace,
// lowercases each entry, and drops empty tokens.
func parseAdminEmails(raw string) []string {
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.ToLower(strings.TrimSpace(p))
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
