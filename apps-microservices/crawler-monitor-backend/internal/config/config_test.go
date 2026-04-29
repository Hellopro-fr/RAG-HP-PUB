package config

import (
	"strings"
	"testing"
)

func setEnv(t *testing.T, kv map[string]string) {
	t.Helper()
	for k, v := range kv {
		t.Setenv(k, v)
	}
}

func TestLoad_AllRequiredPresent(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":           "redis://localhost:6379",
		"ADMIN_PASSWORD_HASH": "scrypt$1$2$3$4$5",
		"JWT_SECRET":          "secret",
	})
	c, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if c.Port != "3001" {
		t.Errorf("Port default = %q, want 3001", c.Port)
	}
	if c.RateLimitMax != 600 {
		t.Errorf("RateLimitMax default = %d, want 600", c.RateLimitMax)
	}
	if c.RateLimitWindowMs != 900000 {
		t.Errorf("RateLimitWindowMs default = %d, want 900000", c.RateLimitWindowMs)
	}
	if c.CrawlerStoragePath != "/app/storage" {
		t.Errorf("CrawlerStoragePath default = %q, want /app/storage", c.CrawlerStoragePath)
	}
}

func TestLoad_MissingRedisURL(t *testing.T) {
	setEnv(t, map[string]string{
		"ADMIN_PASSWORD_HASH": "x",
		"JWT_SECRET":          "x",
	})
	t.Setenv("REDIS_URL", "")
	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "REDIS_URL") {
		t.Fatalf("expect REDIS_URL error, got %v", err)
	}
}

func TestLoad_MissingAdminHash(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":  "redis://x",
		"JWT_SECRET": "x",
	})
	t.Setenv("ADMIN_PASSWORD_HASH", "")
	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "ADMIN_PASSWORD_HASH") {
		t.Fatalf("expect ADMIN_PASSWORD_HASH error, got %v", err)
	}
}

func TestLoad_MissingJWTSecret(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":           "redis://x",
		"ADMIN_PASSWORD_HASH": "x",
	})
	t.Setenv("JWT_SECRET", "")
	_, err := Load()
	if err == nil || !strings.Contains(err.Error(), "JWT_SECRET") {
		t.Fatalf("expect JWT_SECRET error, got %v", err)
	}
}

func TestLoad_CorsAllowedOriginsCSV(t *testing.T) {
	setEnv(t, map[string]string{
		"REDIS_URL":            "redis://x",
		"ADMIN_PASSWORD_HASH":  "x",
		"JWT_SECRET":           "x",
		"CORS_ALLOWED_ORIGINS": "https://a.example,https://b.example",
	})
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(c.CorsAllowedOrigins) != 2 || c.CorsAllowedOrigins[0] != "https://a.example" {
		t.Errorf("CorsAllowedOrigins = %v", c.CorsAllowedOrigins)
	}
}
