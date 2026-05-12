// Package config loads runtime configuration from environment variables.
// All values are read once at boot; nothing in this package is mutated after Load().
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config holds all runtime configuration for mcp-zoho-service.
type Config struct {
	Port            int
	MySQLDSN        string
	EncryptionKey   string
	GatewayToken    string
	SelfURL         string
	CacheTTL        time.Duration
	UpstreamTimeout time.Duration
	LogLevel        string
}

// Load reads environment variables and returns a populated Config or an error
// when a required variable is missing or malformed.
func Load() (*Config, error) {
	c := &Config{
		Port:            envInt("ZOHO_ROUTER_PORT", 8596),
		MySQLDSN:        os.Getenv("MYSQL_DSN"),
		EncryptionKey:   os.Getenv("ENCRYPTION_KEY"),
		GatewayToken:    os.Getenv("ZOHO_GATEWAY_TOKEN"),
		SelfURL:         os.Getenv("ZOHO_SELF_URL"),
		CacheTTL:        time.Duration(envInt("ZOHO_ROUTING_CACHE_TTL", 60)) * time.Second,
		UpstreamTimeout: time.Duration(envInt("ZOHO_UPSTREAM_TIMEOUT", 30)) * time.Second,
		LogLevel:        envDefault("LOG_LEVEL", "info"),
	}

	if c.MySQLDSN == "" {
		return nil, fmt.Errorf("MYSQL_DSN is required")
	}
	if c.EncryptionKey == "" {
		return nil, fmt.Errorf("ENCRYPTION_KEY is required")
	}
	if c.GatewayToken == "" {
		return nil, fmt.Errorf("ZOHO_GATEWAY_TOKEN is required")
	}
	if c.SelfURL == "" {
		return nil, fmt.Errorf("ZOHO_SELF_URL is required (used to exclude the service's own row when picking the admin upstream)")
	}
	return c, nil
}

func envDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
