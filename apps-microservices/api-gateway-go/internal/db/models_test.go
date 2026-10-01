package db

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestTableNames(t *testing.T) {
	require.Equal(t, "info_refresh_token", InfoRefreshToken{}.TableName())
	require.Equal(t, "info_access_token", InfoAccessToken{}.TableName())
	require.Equal(t, "api_call_history", ApiCallHistory{}.TableName())
}
