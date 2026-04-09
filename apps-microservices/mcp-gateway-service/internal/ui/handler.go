package ui

import (
	"embed"
	"io/fs"
	"net/http"
)

//go:embed all:static
var staticFiles embed.FS

// Register mounts the UI routes on the given mux.
func Register(mux *http.ServeMux) {
	subFS, _ := fs.Sub(staticFiles, "static")
	fileServer := http.FileServer(http.FS(subFS))

	// Root redirects to UI
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			http.Redirect(w, r, "/ui/", http.StatusSeeOther)
			return
		}
		http.NotFound(w, r)
	})

	mux.HandleFunc("/ui", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/ui/", http.StatusMovedPermanently)
	})
	mux.Handle("/ui/", http.StripPrefix("/ui/", fileServer))
}
