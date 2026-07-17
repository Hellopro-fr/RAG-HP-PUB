package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildServiceMapFromEnv(t *testing.T) {
	t.Setenv("SERVICE_DLQ", "http://dlq:1234")
	t.Setenv("SERVICE_GRAPHDLQ", "http://graphdlq:5678")
	t.Setenv("OTHER_VAR", "ignored")

	m := BuildServiceMap()

	require.Equal(t, "http://dlq:1234", m["/dlq-service"])
	require.Equal(t, "http://graphdlq:5678", m["/graphdlq-service"])
	require.NotContains(t, m, "OTHER_VAR")
}

func TestExcludedRoutes(t *testing.T) {
	er := BuildExcludedRoutes()
	require.Equal(t, []string{"dlq/queues"}, er["graphdlq-service"])
}

func TestDownstreamTimeouts(t *testing.T) {
	to := BuildDownstreamTimeouts()
	v, ok := to["api-detection-langue-fr-service"]
	require.True(t, ok)
	require.Equal(t, 180.0, v)
}

func TestExcludedServices(t *testing.T) {
	es := ExcludedServices()
	require.Contains(t, es, "crawling-service")
	require.Contains(t, es, "image_comparator-service")
	require.Contains(t, es, "graphadmin-service")
}
