package proxy

import (
	"log"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

var excludedWSHeaders = map[string]struct{}{
	"connection": {}, "upgrade": {}, "host": {},
	"sec-websocket-key": {}, "sec-websocket-version": {}, "sec-websocket-protocol": {}, "sec-websocket-extensions": {},
}

var clientUpgrader = websocket.Upgrader{
	CheckOrigin: func(*http.Request) bool { return true },
}

// NewWSHandler returns a Gin handler that upgrades WebSocket requests and relays
// frames bidirectionally to a downstream service. Non-WebSocket requests fall
// through to subsequent handlers via c.Next().
// services is a snapshot getter so live route updates from the catalog
// refresher are picked up per request without rebuilding the handler.
func NewWSHandler(services func() map[string]string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !websocket.IsWebSocketUpgrade(c.Request) {
			c.Next()
			return
		}
		service := c.Param("service")
		path := strings.TrimPrefix(c.Param("path"), "/")
		base, ok := services()["/"+service]
		if !ok {
			log.Printf("[ws] service %s unknown", service)
			http.Error(c.Writer, "service unknown", http.StatusNotFound)
			c.Abort()
			return
		}
		base = strings.Replace(base, "http://", "ws://", 1)
		base = strings.Replace(base, "https://", "wss://", 1)
		target := strings.TrimRight(base, "/") + "/" + path
		if c.Request.URL.RawQuery != "" {
			target += "?" + c.Request.URL.RawQuery
		}

		fwd := http.Header{}
		for k, vs := range c.Request.Header {
			if _, skip := excludedWSHeaders[strings.ToLower(k)]; skip {
				continue
			}
			for _, v := range vs {
				fwd.Add(k, v)
			}
		}

		clientConn, err := clientUpgrader.Upgrade(c.Writer, c.Request, nil)
		if err != nil {
			log.Printf("[ws] client upgrade failed: %v", err)
			c.Abort()
			return
		}
		defer clientConn.Close()

		backendConn, _, err := websocket.DefaultDialer.Dial(target, fwd)
		if err != nil {
			log.Printf("[ws] backend dial %s failed: %v", target, err)
			_ = clientConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(1011, "backend unavailable"))
			c.Abort()
			return
		}
		defer backendConn.Close()

		errCh := make(chan struct{}, 2)
		go relay(clientConn, backendConn, errCh)
		go relay(backendConn, clientConn, errCh)
		<-errCh
		c.Abort()
	}
}

func relay(src, dst *websocket.Conn, done chan<- struct{}) {
	defer func() { done <- struct{}{} }()
	for {
		mt, msg, err := src.ReadMessage()
		if err != nil {
			return
		}
		if err := dst.WriteMessage(mt, msg); err != nil {
			return
		}
	}
}
