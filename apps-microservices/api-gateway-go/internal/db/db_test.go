package db

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildDSN(t *testing.T) {
	dsn := BuildDSN("user", "pw", "h", "3306", "d")
	require.Equal(t, "user:pw@tcp(h:3306)/d?charset=utf8mb4&parseTime=true&loc=UTC", dsn)
}
