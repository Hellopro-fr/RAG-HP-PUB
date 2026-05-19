package auth

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func RequireAdminKey(expected string) gin.HandlerFunc {
	return func(c *gin.Context) {
		got := c.GetHeader("X-Admin-Key")
		if got != expected {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"detail": "Invalid or missing admin key."})
			return
		}
		c.Next()
	}
}
