package openapi

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLoadBaseSpec(t *testing.T) {
	m, err := LoadBaseSpec()
	require.NoError(t, err)
	require.NotNil(t, m)
	// base.yaml must at minimum parse to a non-empty map
	require.NotEmpty(t, m)
}
