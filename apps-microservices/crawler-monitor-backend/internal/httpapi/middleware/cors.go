package middleware

import (
	"net/http"

	"github.com/go-chi/cors"
)

func CORS(allowed []string) func(http.Handler) http.Handler {
	if len(allowed) == 0 {
		allowed = []string{"*"}
	}
	return cors.Handler(cors.Options{
		AllowedOrigins:   allowed,
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Authorization", "Content-Type"},
		AllowCredentials: false,
		MaxAge:           300,
	})
}
