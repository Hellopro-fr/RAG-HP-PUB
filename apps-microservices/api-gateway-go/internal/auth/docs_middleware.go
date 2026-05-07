package auth

import (
	"net/http"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
)

var docsProtectedPaths = map[string]struct{}{
	"/docs":         {},
	"/redoc":        {},
	"/openapi.json": {},
}

// DocsAuthMiddleware mirrors app/core/auth.py:DocsAuthMiddleware. /openapi-public.json
// is intentionally NOT in the protected set (matches Python).
func DocsAuthMiddleware(j *JWT) gin.HandlerFunc {
	return func(c *gin.Context) {
		path := c.Request.URL.Path
		if _, ok := docsProtectedPaths[path]; !ok {
			c.Next()
			return
		}

		s := sessions.Default(c)
		userRaw := s.Get("user")
		if userRaw == nil {
			redirectLogin(c)
			return
		}
		user, ok := userRaw.(map[string]any)
		if !ok {
			redirectLogin(c)
			return
		}
		token, _ := user["token"].(string)
		if token == "" {
			redirectLogin(c)
			return
		}
		if err := j.VerifyDocsToken(token); err != nil {
			s.Clear()
			_ = s.Save()
			redirectLogin(c)
			return
		}
		c.Next()
	}
}

func redirectLogin(c *gin.Context) {
	c.Redirect(http.StatusFound, "/login")
	c.Abort()
}
