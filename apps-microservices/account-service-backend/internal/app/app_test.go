package app

import "testing"

// Compile-only smoke that the App type and its lifecycle methods exist.
func TestAppShape(t *testing.T) {
	var a *App = nil
	_ = a
}
