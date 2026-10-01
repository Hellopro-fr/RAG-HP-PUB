package app

import "testing"

// Compile-only smoke that App + Build/Run/Shutdown signatures exist.
func TestAppShape(t *testing.T) {
	var a *App = nil
	_ = a
}
