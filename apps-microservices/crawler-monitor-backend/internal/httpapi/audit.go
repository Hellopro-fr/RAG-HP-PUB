package httpapi

import (
	"net/http"
	"strconv"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
)

func auditListHandler(as *auditstore.Local) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		f := auditstore.Filter{
			Action: q.Get("action"),
			User:   q.Get("user"),
			Target: q.Get("target"),
		}
		if from := q.Get("from"); from != "" {
			t, err := time.Parse(time.RFC3339, from)
			if err != nil {
				WriteError(w, 400, "Invalid `from` date")
				return
			}
			f.From = t
		}
		if to := q.Get("to"); to != "" {
			t, err := time.Parse(time.RFC3339, to)
			if err != nil {
				WriteError(w, 400, "Invalid `to` date")
				return
			}
			f.To = t
		}
		if l := q.Get("limit"); l != "" {
			if n, err := strconv.Atoi(l); err == nil {
				f.Limit = n
			}
		}
		if o := q.Get("offset"); o != "" {
			if n, err := strconv.Atoi(o); err == nil {
				f.Offset = n
			}
		}
		page, err := as.Read(r.Context(), f)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		WriteJSON(w, 200, page)
	}
}
