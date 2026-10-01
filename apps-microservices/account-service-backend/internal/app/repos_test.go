package app

import "testing"

// Compile-only sanity check on the Repos struct shape.
func TestReposType(t *testing.T) {
	var _ Repos
}
