package app

import (
	"net/http"
	"testing"
)

// Compile-only smoke: exercising registerRoutes with nil deps would panic;
// just check the function exists with the expected signature.
func TestRegisterRoutesType(t *testing.T) {
	var _ func(*http.ServeMux, routeDeps) = registerRoutes
}
