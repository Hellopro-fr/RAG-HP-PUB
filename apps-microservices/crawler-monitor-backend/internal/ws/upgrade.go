package ws

import (
	"net/http"

	"github.com/golang-jwt/jwt/v5"
)

func UpgradeHandler(hub *Hub, jwtSecret string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token := r.URL.Query().Get("token")
		if token == "" {
			http.Error(w, "Authentication required", 401)
			return
		}
		_, err := jwt.Parse(token, func(t *jwt.Token) (any, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrTokenSignatureInvalid
			}
			return []byte(jwtSecret), nil
		})
		if err != nil {
			http.Error(w, "Invalid token", 401)
			return
		}
		conn, err := Upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		c := NewClientConn(hub, conn)
		hub.Register(c.Client)
		c.Run()
	}
}
