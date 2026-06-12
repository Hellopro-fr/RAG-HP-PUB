package config

import (
	"os"
	"strings"
	"testing"
)

func TestLoad_RequiresMandatoryVars(t *testing.T) {
	os.Clearenv()
	if _, err := Load(); err == nil {
		t.Fatal("expected error when MYSQL_DSN is missing")
	}
}

func TestLoad_BuildsDSNFromMySQLComponents(t *testing.T) {
	os.Clearenv()
	t.Setenv("MYSQL_HOST", "mysql")
	t.Setenv("MYSQL_USER", "gateway_user")
	t.Setenv("MYSQL_PASS", "gateway_pass")
	t.Setenv("MYSQL_DB", "gateway_db")
	t.Setenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	t.Setenv("JWT_SECRET", "x")
	t.Setenv("ACCOUNT_PUBLIC_URL", "https://account.hellopro.fr")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	want := "gateway_user:gateway_pass@tcp(mysql:3306)/gateway_db?parseTime=true"
	if cfg.MySQLDSN != want {
		t.Errorf("MySQLDSN=%q want %q", cfg.MySQLDSN, want)
	}
}

func TestLoad_AuthURLHasHelloproDefault(t *testing.T) {
	os.Clearenv()
	t.Setenv("MYSQL_DSN", "x")
	t.Setenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	t.Setenv("JWT_SECRET", "x")
	t.Setenv("ACCOUNT_PUBLIC_URL", "https://account.hellopro.fr")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.AuthURL != "https://www.hellopro.fr/partenaires_externes/info_produit/auth/auth.php" {
		t.Errorf("AuthURL default = %q", cfg.AuthURL)
	}
	if cfg.JWTAlgo != "HS256" {
		t.Errorf("JWTAlgo default = %q", cfg.JWTAlgo)
	}
}

func TestLoad_AppliesDefaults(t *testing.T) {
	os.Clearenv()
	t.Setenv("MYSQL_DSN", "u:p@tcp(localhost:3306)/account_db")
	t.Setenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
	t.Setenv("JWT_SECRET", "x")
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

func TestLoad_MCPGatewayInternalURL(t *testing.T) {
	t.Setenv("MYSQL_DSN", "u:p@tcp(h:3306)/db")
	t.Setenv("ENCRYPTION_KEY", strings.Repeat("a", 64))
	t.Setenv("JWT_SECRET", "s")
	t.Setenv("ACCOUNT_PUBLIC_URL", "http://x")
	t.Setenv("MCP_GATEWAY_INTERNAL_URL", "http://mcp-gateway-service:8592/")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	// Trailing slash trimmed.
	if cfg.MCPGatewayInternalURL != "http://mcp-gateway-service:8592" {
		t.Errorf("MCPGatewayInternalURL = %q", cfg.MCPGatewayInternalURL)
	}
}
