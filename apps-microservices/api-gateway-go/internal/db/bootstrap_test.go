package db

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

func newSQLite(t *testing.T) *gorm.DB {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	require.NoError(t, AutoMigrate(g))
	return g
}

type fakeIssuer struct{ counter int }

func (f *fakeIssuer) NewRefreshToken(service string) string {
	f.counter++
	return service + "-refresh-token"
}

func TestBootstrapCreatesMissing(t *testing.T) {
	g := newSQLite(t)
	iss := &fakeIssuer{}
	serviceMap := map[string]string{
		"/dlq-service":      "http://dlq",
		"/graphdlq-service": "http://graphdlq",
	}

	require.NoError(t, BootstrapRefreshTokens(context.Background(), g, serviceMap, iss))

	var rows []InfoRefreshToken
	require.NoError(t, g.Find(&rows).Error)
	require.Len(t, rows, 2)
	require.Equal(t, 2, iss.counter)
}

func TestBootstrapSkipsExisting(t *testing.T) {
	g := newSQLite(t)
	iss := &fakeIssuer{}

	require.NoError(t, g.Create(&InfoRefreshToken{NomService: "dlq-service", Token: "x", IPCreation: "system", EstActif: true}).Error)

	require.NoError(t, BootstrapRefreshTokens(context.Background(), g, map[string]string{
		"/dlq-service": "http://dlq",
	}, iss))

	require.Equal(t, 0, iss.counter)
}
