package ws

import (
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
)

// UpgradeHandler authentifie la connexion WebSocket puis la promeut.
// Token absent -> 401 avant upgrade. Token present mais invalide -> l'upgrade
// est accepte puis la connexion est fermee avec le code 1008 (policy
// violation) : le navigateur ne voit pas le corps d'un 401 sur un handshake
// WebSocket, mais il lit event.code / event.reason.
func UpgradeHandler(hub *Hub, jwtSecret string, allowedOrigins ...string) http.HandlerFunc {
	upgrader := newUpgrader(allowedOrigins)
	return func(w http.ResponseWriter, r *http.Request) {
		token := r.URL.Query().Get("token")
		if token == "" {
			http.Error(w, "Authentication required", 401)
			return
		}
		_, tokenErr := jwt.Parse(token, func(t *jwt.Token) (any, error) {
			return []byte(jwtSecret), nil
		}, jwt.WithValidMethods([]string{"HS256"}))

		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		if tokenErr != nil {
			closeWithPolicy(conn, "invalid_token")
			return
		}
		c := NewClientConn(hub, conn)
		hub.Register(c.Client)
		c.Run()
	}
}

// closeWithPolicy envoie une trame de fermeture 1008 puis ferme la connexion.
func closeWithPolicy(conn *websocket.Conn, reason string) {
	msg := websocket.FormatCloseMessage(websocket.ClosePolicyViolation, reason)
	_ = conn.SetWriteDeadline(time.Now().Add(writeWait))
	_ = conn.WriteMessage(websocket.CloseMessage, msg)
	_ = conn.Close()
}
