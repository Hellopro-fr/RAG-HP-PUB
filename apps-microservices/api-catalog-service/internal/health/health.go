package health

import (
	"fmt"
	"net/http"
)

// Handler returns an HTTP handler that exposes a /healthz liveness endpoint.
func Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "ok")
	})
	return mux
}
