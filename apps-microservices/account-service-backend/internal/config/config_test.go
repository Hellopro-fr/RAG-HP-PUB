package config

import (
	"os"
	"testing"
)

func TestLoad_RequiresMandatoryVars(t *testing.T) {
	os.Clearenv()
	if _, err := Load(); err == nil {
		t.Fatal("expected error when MYSQL_DSN is missing")
	}
}

func TestLoad_AppliesDefaults(t *testing.T) {
	os.Clearenv()
	t.Setenv("MYSQL_DSN", "u:p@tcp(localhost:3306)/account_db")
	t.Setenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	t.Setenv("JWT_SECRET", "x")
	t.Setenv("AUTH_URL", "https://www.hellopro.fr/login")
	t.Setenv("ACCOUNT_PUBLIC_URL", "https://account.hellopro.fr")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Port != 8600 {
		t.Errorf("Port=%d, want 8600", cfg.Port)
	}
	if cfg.DefaultTokenTTL != 60 {
		t.Errorf("DefaultTokenTTL=%d, want 60", cfg.DefaultTokenTTL)
	}
	if cfg.DefaultRefreshTTL != 2592000 {
		t.Errorf("DefaultRefreshTTL=%d, want 2592000", cfg.DefaultRefreshTTL)
	}
	if cfg.AuthCodeTTL != 600 {
		t.Errorf("AuthCodeTTL=%d, want 600", cfg.AuthCodeTTL)
	}
	if !cfg.SecureCookie {
		t.Error("SecureCookie default should be true")
	}
}
