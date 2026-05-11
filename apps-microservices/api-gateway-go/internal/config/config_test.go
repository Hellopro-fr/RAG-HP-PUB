package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLoadDefaults(t *testing.T) {
	t.Setenv("JWT_SECRET", "s")
	t.Setenv("GATEWAY_ADMIN_KEY", "k")

	cfg := Load()

	require.Equal(t, "s", cfg.JWTSecret)
	require.Equal(t, "HS256", cfg.JWTAlgo)
	require.Equal(t, "hellopro", cfg.JWTAudience)
	require.Equal(t, "k", cfg.GatewayAdminKey)
	require.Equal(t, 15, cfg.AccessTokenExpireMinutes)
	require.Equal(t, "gateway-mysql", cfg.MySQLHost)
	require.Equal(t, "3306", cfg.MySQLPort)
	require.Equal(t, "gateway_user", cfg.MySQLUser)
	require.Equal(t, "gateway_pass", cfg.MySQLPass)
	require.Equal(t, "gateway_db", cfg.MySQLDB)
	require.Equal(t, "api-gateway", cfg.ServiceName)
}

func TestLoadOverrides(t *testing.T) {
	t.Setenv("JWT_SECRET", "x")
	t.Setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
	t.Setenv("MYSQL_HOST", "db.local")
	t.Setenv("SECURE_COOKIE", "true")
	t.Setenv("GATEWAY_DOCS_ADMIN_EMAILS", " a@b.com ,B@C.com ")

	cfg := Load()

	require.Equal(t, 60, cfg.AccessTokenExpireMinutes)
	require.Equal(t, "db.local", cfg.MySQLHost)
	require.True(t, cfg.SecureCookie)
	require.ElementsMatch(t, []string{"a@b.com", "b@c.com"}, cfg.DocsAdminEmails)
}
