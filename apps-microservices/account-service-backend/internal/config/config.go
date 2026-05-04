package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Configuration struct {
	Port              int
	PublicURL         string
	MySQLDSN          string
	EncryptionKey     string
	JWTSecret         string
	JWTAudience       string
	AuthURL           string
	FallbackUser      string
	FallbackPass      string
	FallbackEmail     string
	AdminEmails       []string
	DefaultTokenTTL   int
	DefaultRefreshTTL int
	AuthCodeTTL       int
	WebhookTimeoutS   int
	WebhookRetries    int
	LogoutWorkers     int
	SecureCookie      bool
	SlackWebhookURL   string
	SlackCooldownS    int
}

func Load() (*Configuration, error) {
	cfg := &Configuration{
		Port:              envInt("ACCOUNT_PORT", 8600),
		PublicURL:         strings.TrimRight(os.Getenv("ACCOUNT_PUBLIC_URL"), "/"),
		MySQLDSN:          os.Getenv("MYSQL_DSN"),
		EncryptionKey:     os.Getenv("ENCRYPTION_KEY"),
		JWTSecret:         os.Getenv("JWT_SECRET"),
		JWTAudience:       envStr("JWT_AUDIENCE", "https://www.hellopro.fr"),
		AuthURL:           os.Getenv("AUTH_URL"),
		FallbackUser:      os.Getenv("FALLBACK_USER"),
		FallbackPass:      os.Getenv("FALLBACK_PASS"),
		FallbackEmail:     os.Getenv("FALLBACK_EMAIL"),
		AdminEmails:       splitCSV(os.Getenv("ADMIN_EMAILS")),
		DefaultTokenTTL:   envInt("OAUTH2_DEFAULT_TOKEN_TTL", 60),
		DefaultRefreshTTL: envInt("OAUTH2_DEFAULT_REFRESH_TTL", 2592000),
		AuthCodeTTL:       envInt("OAUTH2_AUTH_CODE_TTL", 600),
		WebhookTimeoutS:   envInt("LOGOUT_WEBHOOK_TIMEOUT", 5),
		WebhookRetries:    envInt("LOGOUT_WEBHOOK_RETRIES", 3),
		LogoutWorkers:     envInt("LOGOUT_WORKERS", 4),
		SecureCookie:      envBool("SECURE_COOKIE", true),
		SlackWebhookURL:   os.Getenv("SLACK_WEBHOOK_URL"),
		SlackCooldownS:    envInt("SLACK_AUTH_ALERT_COOLDOWN", 600),
	}
	if err := cfg.validate(); err != nil {
		return nil, err
	}
	return cfg, nil
}

func (c *Configuration) validate() error {
	if c.MySQLDSN == "" {
		return fmt.Errorf("MYSQL_DSN is required")
	}
	if c.EncryptionKey == "" || len(c.EncryptionKey) != 64 {
		return fmt.Errorf("ENCRYPTION_KEY must be 32 bytes hex (64 chars)")
	}
	if c.JWTSecret == "" {
		return fmt.Errorf("JWT_SECRET is required")
	}
	if c.AuthURL == "" {
		return fmt.Errorf("AUTH_URL is required")
	}
	if c.PublicURL == "" {
		return fmt.Errorf("ACCOUNT_PUBLIC_URL is required")
	}
	return nil
}

func envStr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func envInt(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envBool(k string, def bool) bool {
	if v := os.Getenv(k); v != "" {
		return v == "1" || strings.EqualFold(v, "true") || strings.EqualFold(v, "yes")
	}
	return def
}

func splitCSV(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}
