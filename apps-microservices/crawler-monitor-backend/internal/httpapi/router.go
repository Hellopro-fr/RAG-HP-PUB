package httpapi

import (
	"net/http"

	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version string
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Get("/health", healthHandler(d.Version))
	return r
}
