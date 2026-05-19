package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	cachepkg "api-gateway-go/internal/cache"
	dbpkg "api-gateway-go/internal/db"
)

// APITokenVerifier validates Bearer tokens on proxied requests.
// It mirrors app/core/auth.py:verify_api_token (Python source lines 112-195).
type APITokenVerifier struct {
	jwt            *JWT
	db             *gorm.DB
	cache          *cachepkg.Cache
	excludedRoutes map[string][]string
}

// NewAPITokenVerifier constructs a verifier with the given dependencies.
// excludedRoutes maps service name → list of path prefixes that bypass auth.
func NewAPITokenVerifier(j *JWT, g *gorm.DB, c *cachepkg.Cache, excluded map[string][]string) *APITokenVerifier {
	return &APITokenVerifier{jwt: j, db: g, cache: c, excludedRoutes: excluded}
}

// Middleware mirrors app/core/auth.py:verify_api_token, including the existing
// TODO short-circuit that bypasses auth for every service except graphdlq-service.
// DO NOT remove this short-circuit without a follow-up spec — the Python service
// has the same behavior in production.
func (v *APITokenVerifier) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		service := c.Param("service")
		path := strings.Trim(c.Param("path"), "/")

		// TODO: Test pour toujours exclure toutes les routes
		// → except graphdlq-service pour le test (ported from Python auth.py:118-123).
		if service != "graphdlq-service" {
			c.Set("token_payload", gin.H{"sub": service, "is_excluded": true})
			c.Next()
			return
		}

		// 1. Excluded routes bypass authentication.
		for _, p := range v.excludedRoutes[service] {
			if p == path {
				c.Set("token_payload", gin.H{"sub": service, "is_excluded": true})
				c.Next()
				return
			}
		}

		// 2. Bearer token extraction.
		authHeader := c.GetHeader("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			abortAuth(c, "Access token manquant ou invalide.")
			return
		}
		raw := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))

		// 3. Verify JWT signature and expiry.
		claims, err := v.jwt.VerifyAccessToken(raw)
		if err != nil {
			if errors.Is(err, ErrExpired) {
				abortAuth(c, "Access token has expired. Please refresh.")
			} else {
				abortAuth(c, "Invalid access token.")
			}
			return
		}

		// 4. Redis fast path — cache hit means token is live.
		ctx := c.Request.Context()
		var redisPayload map[string]any
		found, _ := v.cache.GetJSON(ctx, "access_token:"+raw, &redisPayload)
		if found {
			c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
			c.Next()
			return
		}

		// 5. DB fallback — verify token is active and its refresh token has not been revoked.
		if !v.dbAccessTokenActive(ctx, raw) {
			abortAuth(c, "Access token has been revoked or expired.")
			return
		}
		c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
		c.Next()
	}
}

func abortAuth(c *gin.Context, detail string) {
	c.Header("WWW-Authenticate", "Bearer")
	c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"detail": detail})
}

func (v *APITokenVerifier) dbAccessTokenActive(ctx context.Context, token string) bool {
	now := time.Now().UTC()
	var access dbpkg.InfoAccessToken
	err := v.db.WithContext(ctx).
		Preload("RefreshToken").
		Where("token = ? AND est_actif = ? AND date_expiration >= ?", token, true, now).
		First(&access).Error
	if err != nil {
		return false
	}
	return access.RefreshToken.EstActif
}
