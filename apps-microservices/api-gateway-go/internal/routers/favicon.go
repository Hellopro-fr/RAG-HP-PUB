package routers

import (
	_ "embed"

	"github.com/gin-gonic/gin"
)

//go:embed assets/favicon.svg
var faviconSVG []byte

// RegisterFavicon serves the Hellopro logo as the gateway favicon.
// Browsers request /favicon.ico by default; modern browsers also pick up
// /favicon.svg via <link rel="icon" type="image/svg+xml">. Both serve the
// same SVG with Content-Type image/svg+xml — there is no .ico container.
func RegisterFavicon(r *gin.Engine) {
	handler := func(c *gin.Context) {
		c.Data(200, "image/svg+xml", faviconSVG)
	}
	r.GET("/favicon.ico", handler)
	r.GET("/favicon.svg", handler)
}
