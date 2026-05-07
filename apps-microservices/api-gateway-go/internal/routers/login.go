package routers

import (
	"net/http"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
)

func RegisterLogin(r *gin.Engine, j *auth.JWT) {
	r.GET("/login", func(c *gin.Context) {
		s := sessions.Default(c)
		userRaw := s.Get("user")
		if user, ok := userRaw.(map[string]any); ok {
			if tok, ok := user["token"].(string); ok && tok != "" {
				if err := j.VerifyDocsToken(tok); err == nil {
					c.Redirect(http.StatusSeeOther, "/docs")
					return
				}
				s.Clear()
				_ = s.Save()
			}
		}
		c.Redirect(http.StatusFound, "/auth/login")
	})

	r.GET("/logout", func(c *gin.Context) {
		s := sessions.Default(c)
		s.Clear()
		_ = s.Save()
		c.Redirect(http.StatusSeeOther, "/login")
	})
}
