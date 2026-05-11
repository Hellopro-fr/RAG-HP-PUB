package proxy

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
)

func TestWebSocketEcho(t *testing.T) {
	up := websocket.Upgrader{}
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := up.Upgrade(w, r, nil)
		require.NoError(t, err)
		defer conn.Close()
		for {
			_, msg, err := conn.ReadMessage()
			if err != nil {
				return
			}
			_ = conn.WriteMessage(websocket.TextMessage, append([]byte("echo:"), msg...))
		}
	}))
	defer backend.Close()

	gin.SetMode(gin.TestMode)
	r := gin.New()
	wsHandler := NewWSHandler(map[string]string{"/svc-service": strings.Replace(backend.URL, "http://", "ws://", 1)})
	r.GET("/:service/*path", wsHandler)

	gw := httptest.NewServer(r)
	defer gw.Close()
	gwURL, _ := url.Parse(gw.URL)
	gwURL.Scheme = "ws"
	gwURL.Path = "/svc-service/anything"

	conn, _, err := websocket.DefaultDialer.Dial(gwURL.String(), nil)
	require.NoError(t, err)
	defer conn.Close()
	require.NoError(t, conn.WriteMessage(websocket.TextMessage, []byte("hello")))
	_ = conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, msg, err := conn.ReadMessage()
	require.NoError(t, err)
	require.Equal(t, "echo:hello", string(msg))
}
