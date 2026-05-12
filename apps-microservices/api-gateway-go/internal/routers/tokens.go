package routers

import (
	"context"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"api-gateway-go/internal/auth"
	cachepkg "api-gateway-go/internal/cache"
	dbpkg "api-gateway-go/internal/db"
)

const maxActiveAccessTokens = 10

// TokenDeps holds all dependencies for the token route handlers.
type TokenDeps struct {
	DB                       *gorm.DB
	Cache                    *cachepkg.Cache
	JWT                      *auth.JWT
	AdminKey                 string
	AccessTokenExpireMinutes int
}

type tokenGenerateReq struct {
	ServiceName string `json:"service_name" binding:"required"`
}

type tokenGenerateResp struct {
	ServiceName               string    `json:"service_name"`
	RefreshToken              string    `json:"refresh_token"`
	AccessToken               string    `json:"access_token"`
	AccessTokenExpiresMinutes int       `json:"access_token_expires_minutes"`
	AccessTokenExpiresAt      time.Time `json:"access_token_expires_at"`
	CreatedAt                 time.Time `json:"created_at"`
}

type tokenRefreshReq struct {
	ServiceName  string `json:"service_name" binding:"required"`
	RefreshToken string `json:"refresh_token" binding:"required"`
}

type tokenRefreshResp struct {
	ServiceName               string    `json:"service_name"`
	AccessToken               string    `json:"access_token"`
	AccessTokenExpiresMinutes int       `json:"access_token_expires_minutes"`
	AccessTokenExpiresAt      time.Time `json:"access_token_expires_at"`
}

type tokenRevokeReq struct {
	ServiceName string `json:"service_name" binding:"required"`
}

type tokenRevokeResp struct {
	ServiceName string `json:"service_name"`
	Revoked     bool   `json:"revoked"`
	Message     string `json:"message"`
}

// RegisterTokens registers all /auth/* token and log routes.
func RegisterTokens(r *gin.Engine, d TokenDeps) {
	g := r.Group("/auth")
	g.POST("/token/generate", auth.RequireAdminKey(d.AdminKey), generateHandler(d))
	g.POST("/token/refresh", refreshHandler(d))
	g.POST("/token/revoke", auth.RequireAdminKey(d.AdminKey), revokeHandler(d))
	g.GET("/token/refresh-tokens", listRefreshHandler(d))
	g.GET("/token/all-refresh-tokens", auth.RequireAdminKey(d.AdminKey), listAllRefreshHandler(d))
	g.GET("/logs", auth.RequireAdminKey(d.AdminKey), logsHandler(d))
}

func generateHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body tokenGenerateReq
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": err.Error()})
			return
		}
		ctx := c.Request.Context()

		// Reuse existing active refresh token for this service if present.
		var rt dbpkg.InfoRefreshToken
		err := d.DB.WithContext(ctx).
			Where("nom_service = ? AND est_actif = ?", body.ServiceName, true).
			First(&rt).Error
		if err == gorm.ErrRecordNotFound {
			rt = dbpkg.InfoRefreshToken{
				NomService: body.ServiceName,
				Token:      d.JWT.GenerateRefreshToken(body.ServiceName),
				IPCreation: clientIP(c),
				EstActif:   true,
			}
			if err := d.DB.WithContext(ctx).Create(&rt).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
				return
			}
		} else if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}

		access := d.JWT.GenerateAccessToken(body.ServiceName, rt.ID)
		exp := time.Now().UTC().Add(time.Duration(d.AccessTokenExpireMinutes) * time.Minute)
		acc := dbpkg.InfoAccessToken{
			IDRefreshToken: rt.ID,
			Token:          access,
			DateExpiration: exp,
			EstActif:       true,
		}
		if err := d.DB.WithContext(ctx).Create(&acc).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}
		_ = d.Cache.SetJSON(ctx, "access_token:"+access,
			map[string]any{"service": body.ServiceName, "rtid": rt.ID},
			time.Duration(d.AccessTokenExpireMinutes)*time.Minute)
		_ = pruneAccessTokens(ctx, d.DB, rt.ID)

		c.JSON(http.StatusOK, tokenGenerateResp{
			ServiceName:               body.ServiceName,
			RefreshToken:              rt.Token,
			AccessToken:               access,
			AccessTokenExpiresMinutes: d.AccessTokenExpireMinutes,
			AccessTokenExpiresAt:      exp,
			CreatedAt:                 rt.DateCreation,
		})
	}
}

func refreshHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body tokenRefreshReq
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": err.Error()})
			return
		}
		ctx := c.Request.Context()

		var rt dbpkg.InfoRefreshToken
		err := d.DB.WithContext(ctx).
			Where("nom_service = ? AND token = ? AND est_actif = ?", body.ServiceName, body.RefreshToken, true).
			First(&rt).Error
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "invalid or revoked refresh token"})
			return
		}

		access := d.JWT.GenerateAccessToken(body.ServiceName, rt.ID)
		exp := time.Now().UTC().Add(time.Duration(d.AccessTokenExpireMinutes) * time.Minute)
		_ = d.DB.WithContext(ctx).Create(&dbpkg.InfoAccessToken{
			IDRefreshToken: rt.ID,
			Token:          access,
			DateExpiration: exp,
			EstActif:       true,
		})
		_ = d.Cache.SetJSON(ctx, "access_token:"+access,
			map[string]any{"service": body.ServiceName, "rtid": rt.ID},
			time.Duration(d.AccessTokenExpireMinutes)*time.Minute)
		_ = pruneAccessTokens(ctx, d.DB, rt.ID)

		c.JSON(http.StatusOK, tokenRefreshResp{
			ServiceName:               body.ServiceName,
			AccessToken:               access,
			AccessTokenExpiresMinutes: d.AccessTokenExpireMinutes,
			AccessTokenExpiresAt:      exp,
		})
	}
}

func revokeHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		var body tokenRevokeReq
		if err := c.ShouldBindJSON(&body); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": err.Error()})
			return
		}
		ctx := c.Request.Context()

		var rts []dbpkg.InfoRefreshToken
		if err := d.DB.WithContext(ctx).
			Where("nom_service = ? AND est_actif = ?", body.ServiceName, true).
			Find(&rts).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}
		if len(rts) == 0 {
			c.JSON(http.StatusOK, tokenRevokeResp{
				ServiceName: body.ServiceName,
				Revoked:     false,
				Message:     "no active token found for this service",
			})
			return
		}

		ids := make([]int64, len(rts))
		for i, r := range rts {
			ids[i] = r.ID
		}
		_ = d.DB.WithContext(ctx).Model(&dbpkg.InfoRefreshToken{}).
			Where("id IN ?", ids).Update("est_actif", false)
		_ = d.DB.WithContext(ctx).Model(&dbpkg.InfoAccessToken{}).
			Where("id_refresh_token_id IN ? AND est_actif = ?", ids, true).Update("est_actif", false)

		// Evict access tokens from cache.
		var accs []dbpkg.InfoAccessToken
		_ = d.DB.WithContext(ctx).Where("id_refresh_token_id IN ?", ids).Find(&accs).Error
		for _, a := range accs {
			_ = d.Cache.Delete(ctx, "access_token:"+a.Token)
		}

		c.JSON(http.StatusOK, tokenRevokeResp{
			ServiceName: body.ServiceName,
			Revoked:     true,
			Message:     "refresh token revoked",
		})
	}
}

// pruneAccessTokens keeps only the 10 most-recent non-expired active access tokens
// per refresh token and deactivates any expired-but-still-active rows.
// Mirrors the Python api-gateway behaviour.
func pruneAccessTokens(ctx context.Context, gdb *gorm.DB, refreshID int64) error {
	now := time.Now().UTC()

	// Deactivate expired rows first.
	_ = gdb.WithContext(ctx).Model(&dbpkg.InfoAccessToken{}).
		Where("id_refresh_token_id = ? AND est_actif = ? AND date_expiration < ?", refreshID, true, now).
		Update("est_actif", false)

	// Find remaining active non-expired tokens, newest first.
	var active []dbpkg.InfoAccessToken
	if err := gdb.WithContext(ctx).
		Where("id_refresh_token_id = ? AND est_actif = ? AND date_expiration >= ?", refreshID, true, now).
		Order("date_creation DESC").
		Find(&active).Error; err != nil {
		return err
	}
	if len(active) <= maxActiveAccessTokens {
		return nil
	}

	excessIDs := make([]int64, 0, len(active)-maxActiveAccessTokens)
	for _, a := range active[maxActiveAccessTokens:] {
		excessIDs = append(excessIDs, a.ID)
	}
	_ = gdb.WithContext(ctx).Model(&dbpkg.InfoAccessToken{}).
		Where("id IN ?", excessIDs).Update("est_actif", false)
	return nil
}

type refreshTokenEntry struct {
	ID           int64   `json:"id"`
	ServiceName  string    `json:"service_name"`
	Token        string    `json:"token"`
	DateCreation time.Time `json:"date_creation"`
	IPCreation   string    `json:"ip_creation"`
	EstActif     bool      `json:"est_actif"`
}

type refreshTokenList struct {
	Total int                  `json:"total"`
	Items []refreshTokenEntry  `json:"items"`
}

type apiCallHistoryEntry struct {
	ID             int64   `json:"id"`
	ServiceName    string    `json:"service_name"`
	Method         string    `json:"method"`
	Path           string    `json:"path"`
	StatusCode     int       `json:"status_code"`
	ClientIP       string    `json:"client_ip"`
	RequestHeaders *string   `json:"request_headers"`
	CalledAt       time.Time `json:"called_at"`
	DurationMs     *int      `json:"duration_ms"`
}

type apiCallHistoryList struct {
	Total    int64                 `json:"total"`
	Page     int                   `json:"page"`
	PageSize int                   `json:"page_size"`
	Items    []apiCallHistoryEntry `json:"items"`
}

func listRefreshHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		serviceName := c.Query("service_name")
		if serviceName == "" {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"detail": "service_name is required"})
			return
		}
		activeOnly := c.DefaultQuery("active_only", "true") != "false"
		ctx := c.Request.Context()
		q := d.DB.WithContext(ctx).Where("nom_service = ?", serviceName)
		if activeOnly {
			q = q.Where("est_actif = ?", true)
		}
		var rows []dbpkg.InfoRefreshToken
		if err := q.Order("nom_service").Find(&rows).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}
		entries := make([]refreshTokenEntry, len(rows))
		for i, r := range rows {
			entries[i] = refreshTokenEntry{
				ID: r.ID, ServiceName: r.NomService, Token: r.Token,
				DateCreation: r.DateCreation, IPCreation: r.IPCreation, EstActif: r.EstActif,
			}
		}
		c.JSON(http.StatusOK, refreshTokenList{Total: len(entries), Items: entries})
	}
}

func listAllRefreshHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		q := d.DB.WithContext(ctx)
		if v, ok := c.GetQuery("active_only"); ok {
			q = q.Where("est_actif = ?", v == "true")
		}
		var rows []dbpkg.InfoRefreshToken
		if err := q.Order("nom_service, date_creation DESC").Find(&rows).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}
		entries := make([]refreshTokenEntry, len(rows))
		for i, r := range rows {
			entries[i] = refreshTokenEntry{
				ID: r.ID, ServiceName: r.NomService, Token: r.Token,
				DateCreation: r.DateCreation, IPCreation: r.IPCreation, EstActif: r.EstActif,
			}
		}
		c.JSON(http.StatusOK, refreshTokenList{Total: len(entries), Items: entries})
	}
}

func logsHandler(d TokenDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		page := atoiDefault(c.DefaultQuery("page", "1"), 1)
		pageSize := atoiDefault(c.DefaultQuery("page_size", "50"), 50)
		if pageSize > 500 {
			pageSize = 500
		}
		serviceName := c.Query("service_name")
		q := d.DB.WithContext(ctx).Model(&dbpkg.ApiCallHistory{})
		if serviceName != "" {
			q = q.Where("service_name = ?", serviceName)
		}
		var total int64
		_ = q.Count(&total).Error
		var rows []dbpkg.ApiCallHistory
		_ = q.Order("called_at DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&rows).Error
		entries := make([]apiCallHistoryEntry, len(rows))
		for i, r := range rows {
			entries[i] = apiCallHistoryEntry{
				ID: r.ID, ServiceName: r.ServiceName, Method: r.Method, Path: r.Path,
				StatusCode: r.StatusCode, ClientIP: r.ClientIP, RequestHeaders: r.RequestHeaders,
				CalledAt: r.CalledAt, DurationMs: r.DurationMs,
			}
		}
		c.JSON(http.StatusOK, apiCallHistoryList{Total: total, Page: page, PageSize: pageSize, Items: entries})
	}
}

func atoiDefault(s string, def int) int {
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 {
		return def
	}
	return n
}

func clientIP(c *gin.Context) string {
	if ip := c.ClientIP(); ip != "" {
		return ip
	}
	return "unknown"
}
