package config

import (
	"os"
	"testing"
	"time"
)

func TestLoad_Defaults(t *testing.T) {
	os.Clearenv()
	os.Setenv("MYSQL_PASS", "x")
	os.Setenv("ADMIN_KEY", "k")
	cfg := Load()
	if cfg.MySQLHost != "gateway-mysql" {
		t.Fatalf("MySQLHost = %q, want gateway-mysql", cfg.MySQLHost)
	}
	if cfg.GRPCPort != 9100 {
		t.Fatalf("GRPCPort = %d, want 9100", cfg.GRPCPort)
	}
	if cfg.ScanInterval != 15*time.Minute {
		t.Fatalf("ScanInterval = %v, want 15m", cfg.ScanInterval)
	}
	if cfg.ScanConcurrency != 16 {
		t.Fatalf("ScanConcurrency = %d, want 16", cfg.ScanConcurrency)
	}
}

func TestLoad_SeedTargetsFromEnv(t *testing.T) {
	os.Clearenv()
	os.Setenv("MYSQL_PASS", "x")
	os.Setenv("ADMIN_KEY", "k")
	os.Setenv("SERVICE_FOO", "http://foo:8000")
	os.Setenv("SERVICE_BAR_BAZ", "http://bar-baz:8001")
	cfg := Load()
	if got := cfg.SeedTargets["foo-service"]; got != "http://foo:8000" {
		t.Fatalf("foo-service = %q", got)
	}
	if got := cfg.SeedTargets["bar_baz-service"]; got != "http://bar-baz:8001" {
		t.Fatalf("bar_baz-service = %q", got)
	}
}
