package authserver

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type ClientLookup interface {
	GetByClientID(id string) (*db.OAuth2Client, error)
}

func NewBrandingHandler(lookup ClientLookup) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("client_id")
		c, err := lookup.GetByClientID(id)
		if err != nil {
			http.Error(w, `{"error":"not_found"}`, http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "public, max-age=60")
		_ = json.NewEncoder(w).Encode(map[string]string{
			"name":        c.Name,
			"logo_url":    c.LogoURL,
			"brand_color": c.BrandColor,
		})
	})
}
