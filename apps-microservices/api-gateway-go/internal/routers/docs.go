package routers

import (
	_ "embed"
	"net/http"
	"strings"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/openapi"
)

//go:embed assets/swagger.html
var swaggerHTML []byte

// DocsDeps holds the dependencies needed by the docs routes.
type DocsDeps struct {
	BaseSpec    map[string]any
	ServiceMap  map[string]string
	AdminEmails map[string]struct{}
	AdminKey    string
}

// RegisterDocs registers /openapi.json, /openapi-public.json, /docs, and /redoc.
func RegisterDocs(r *gin.Engine, d DocsDeps) {
	r.GET("/openapi.json", func(c *gin.Context) {
		spec, _ := openapi.Aggregate(c.Request.Context(), openapi.AggregateInput{
			Base:     d.BaseSpec,
			Services: d.ServiceMap,
		})
		c.JSON(200, spec)
	})

	r.GET("/openapi-public.json", func(c *gin.Context) {
		spec, _ := openapi.Aggregate(c.Request.Context(), openapi.AggregateInput{
			Base:     d.BaseSpec,
			Services: d.ServiceMap,
		})
		c.JSON(200, openapi.Filter(spec))
	})

	r.GET("/docs", func(c *gin.Context) {
		openapiURL := "/openapi-public.json"
		if isAdminSession(c, d.AdminEmails) {
			openapiURL = "/openapi.json"
		}
		out := strings.ReplaceAll(string(swaggerHTML), "__TITLE__", "API Gateway Docs")
		out = strings.ReplaceAll(out, "__OPENAPI_URL__", openapiURL)
		c.Data(200, "text/html; charset=utf-8", []byte(out))
	})

	r.GET("/redoc", func(c *gin.Context) {
		c.Redirect(http.StatusMovedPermanently, "/docs")
	})
}

// isAdminSession returns true when the session contains an email present in adminEmails.
func isAdminSession(c *gin.Context, adminEmails map[string]struct{}) bool {
	s := sessions.Default(c)
	userRaw := s.Get("user")
	if userRaw == nil {
		return false
	}
	user, ok := userRaw.(map[string]any)
	if !ok {
		return false
	}
	email, ok := user["email"].(string)
	if !ok {
		return false
	}
	_, hit := adminEmails[strings.ToLower(strings.TrimSpace(email))]
	return hit
}
