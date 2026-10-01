package auth

import (
	"context"
	"errors"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	cachepkg "api-gateway-go/internal/cache"
	dbpkg "api-gateway-go/internal/db"
)

// APITokenVerifier validates auth on proxied requests per the catalog AuthSnapshot.
// Spec: docs/superpowers/specs/2026-05-28-apitokenverifier-catalog-driven-design.md
type APITokenVerifier struct {
	jwt      *JWT
	db       *gorm.DB
	cache    *cachepkg.Cache
	getSnap  func() AuthSnapshot
	adminKey string

	unknownMu   sync.Mutex
	unknownSeen map[string]time.Time
}

// NewAPITokenVerifier constructs a verifier. getSnap returns the live auth
// snapshot (from the catalog refresher); adminKey gates PolicyAdminKey services.
func NewAPITokenVerifier(j *JWT, g *gorm.DB, c *cachepkg.Cache, getSnap func() AuthSnapshot, adminKey string) *APITokenVerifier {
	return &APITokenVerifier{
		jwt: j, db: g, cache: c, getSnap: getSnap, adminKey: adminKey,
		unknownSeen: map[string]time.Time{},
	}
}

// Middleware resolves the per-request auth policy from the snapshot and enforces it.
// Decision order is handled by AuthSnapshot.PolicyFor (endpoint override → public
// path → service default → PolicyPublic fail-open).
func (v *APITokenVerifier) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		service := c.Param("service")
		path := c.Param("path")
		method := c.Request.Method

		snap := v.getSnap()
		if _, known := snap[service]; !known {
			v.logUnknown(service)
		}
		policy := snap.PolicyFor(service, method, path)

		switch policy {
		case PolicyPublic:
			c.Set("token_payload", gin.H{"sub": service, "is_excluded": true})
			c.Next()
			return
		case PolicyAdminKey:
			if v.adminKey == "" || c.GetHeader("X-Admin-Key") != v.adminKey {
				c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"detail": "Invalid or missing admin key."})
				return
			}
			c.Set("token_payload", gin.H{"sub": service, "is_admin": true})
			c.Next()
			return
		case PolicyBearer:
			// fall through to bearer flow below
		}

		authHeader := c.GetHeader("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			abortAuth(c, "Access token manquant ou invalide.")
			return
		}
		raw := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))

		claims, err := v.jwt.VerifyAccessToken(raw)
		if err != nil {
			if errors.Is(err, ErrExpired) {
				abortAuth(c, "Access token has expired. Please refresh.")
			} else {
				abortAuth(c, "Invalid access token.")
			}
			return
		}

		ctx := c.Request.Context()
		if v.cache != nil {
			var redisPayload map[string]any
			found, _ := v.cache.GetJSON(ctx, "access_token:"+raw, &redisPayload)
			if found {
				c.Set("token_payload", gin.H{"sub": claims.Subject, "rtid": claims.RefreshTokenID})
				c.Next()
				return
			}
		}

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
	if v.db == nil {
		return false
	}
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

// logUnknown emits at most one WARN per service per hour (avoids log spam when an
// unregistered service is hit and we fail open to PolicyPublic).
func (v *APITokenVerifier) logUnknown(service string) {
	v.unknownMu.Lock()
	defer v.unknownMu.Unlock()
	if last, ok := v.unknownSeen[service]; ok && time.Since(last) < time.Hour {
		return
	}
	v.unknownSeen[service] = time.Now()
	log.Printf("[verifier] WARN unknown service=%q not in AuthSnapshot; failing open", service)
}
