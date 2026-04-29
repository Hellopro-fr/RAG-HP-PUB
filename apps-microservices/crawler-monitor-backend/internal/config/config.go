package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Port               string
	RedisURL           string
	CrawlerStoragePath string
	AdminPasswordHash  string
	JWTSecret          string
	CorsAllowedOrigins []string
	TrustProxyHops     int
	RateLimitMax       int
	RateLimitWindowMs  int
	ReplayHighCPU      float64
	AuditLogDir        string
	AuditRetentionDays int
}

func Load() (*Config, error) {
	c := &Config{
		Port:               envOr("PORT", "3001"),
		RedisURL:           os.Getenv("REDIS_URL"),
		CrawlerStoragePath: envOr("CRAWLER_STORAGE_PATH", "/app/storage"),
		AdminPasswordHash:  os.Getenv("ADMIN_PASSWORD_HASH"),
		JWTSecret:          os.Getenv("JWT_SECRET"),
		TrustProxyHops:     envInt("TRUST_PROXY", 1),
		RateLimitMax:       envInt("RATE_LIMIT_MAX", 600),
		RateLimitWindowMs:  envInt("RATE_LIMIT_WINDOW_MS", 900000),
		ReplayHighCPU:      envFloat("REPLAY_HIGH_CPU", 0.85),
		AuditLogDir:        envOr("AUDIT_LOG_DIR", "./logs/audit/"),
		AuditRetentionDays: envInt("AUDIT_RETENTION_DAYS", 90),
	}

	if origins := os.Getenv("CORS_ALLOWED_ORIGINS"); origins != "" {
		for _, o := range strings.Split(origins, ",") {
			if t := strings.TrimSpace(o); t != "" {
				c.CorsAllowedOrigins = append(c.CorsAllowedOrigins, t)
			}
		}
	}

	if c.RedisURL == "" {
		return nil, fmt.Errorf("REDIS_URL is required")
	}
	if c.AdminPasswordHash == "" {
		return nil, fmt.Errorf("ADMIN_PASSWORD_HASH is required (scrypt format)")
	}
	if c.JWTSecret == "" {
		return nil, fmt.Errorf("JWT_SECRET is required")
	}
	return c, nil
}

func envOr(key, def string) string {
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

func envFloat(key string, def float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}
