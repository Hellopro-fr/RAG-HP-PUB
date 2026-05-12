package routers

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"

	"api-gateway-go/internal/sso"
)

// SSODeps holds all dependencies for the SSO route handlers.
type SSODeps struct {
	Resolver        *sso.Resolver
	AccountBaseURL  string // internal base URL for token exchange (server-to-server)
	AccountPubURL   string // public-facing base URL for browser redirects
	AccountRedirect string // redirect_uri sent to the authorization server
	SecureCookie    bool
	HTTPClient      *http.Client
}

// replayWindowS is the maximum allowed age (in seconds) of a logout webhook event.
const replayWindowS = 5 * 60

// RegisterSSO registers /auth/login, /auth/callback, and /auth/logout-webhook on r.
func RegisterSSO(r *gin.Engine, d SSODeps) {
	if d.HTTPClient == nil {
		d.HTTPClient = &http.Client{Timeout: 10 * time.Second}
	}
	r.GET("/auth/login", authLoginHandler(d))
	r.GET("/auth/callback", authCallbackHandler(d))
	r.POST("/auth/logout-webhook", logoutWebhookHandler(d))
}

// redirectURI returns the configured redirect URI or falls back to the first
// registered URI returned by the account service.
func redirectURI(d SSODeps, c *sso.ClientCredentials) (string, error) {
	if d.AccountRedirect != "" {
		return d.AccountRedirect, nil
	}
	if len(c.RedirectURIs) > 0 {
		return c.RedirectURIs[0], nil
	}
	return "", fmt.Errorf("no redirect_uri available (set ACCOUNT_REDIRECT_URI or register one)")
}

// authLoginHandler initiates the PKCE authorization code flow.
// Stores the verifier and state in short-lived HttpOnly cookies.
func authLoginHandler(d SSODeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		creds, err := d.Resolver.Resolve(c.Request.Context())
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": fmt.Sprintf("account-service credentials unavailable: %v", err)})
			return
		}
		ru, err := redirectURI(d, creds)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}
		p := sso.NewPKCEPair()
		target := fmt.Sprintf(
			"%s/authorize?response_type=code&client_id=%s&redirect_uri=%s&code_challenge=%s&code_challenge_method=S256&state=%s",
			d.AccountPubURL,
			url.QueryEscape(creds.ClientID),
			url.QueryEscape(ru),
			p.Challenge,
			p.State,
		)
		setShortCookie(c, "auth_verifier", p.Verifier, d.SecureCookie)
		setShortCookie(c, "auth_state", p.State, d.SecureCookie)
		c.Redirect(http.StatusFound, target)
	}
}

// setShortCookie sets a short-lived (10 min) HttpOnly cookie for PKCE state.
func setShortCookie(c *gin.Context, name, value string, secure bool) {
	c.SetSameSite(http.SameSiteLaxMode)
	c.SetCookie(name, value, 600, "/", "", secure, true)
}

// authCallbackHandler exchanges the authorization code for tokens, validates
// the PKCE state, stores user info in the session, and redirects to /docs.
func authCallbackHandler(d SSODeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		code := c.Query("code")
		state := c.Query("state")
		if code == "" || state == "" {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "missing code or state"})
			return
		}
		storedState, _ := c.Cookie("auth_state")
		verifier, _ := c.Cookie("auth_verifier")
		if storedState != state {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "state mismatch"})
			return
		}
		if verifier == "" {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "missing verifier"})
			return
		}
		creds, err := d.Resolver.Resolve(c.Request.Context())
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": fmt.Sprintf("account-service credentials unavailable: %v", err)})
			return
		}
		ru, err := redirectURI(d, creds)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
			return
		}

		form := url.Values{}
		form.Set("grant_type", "authorization_code")
		form.Set("code", code)
		form.Set("redirect_uri", ru)
		form.Set("code_verifier", verifier)

		req, _ := http.NewRequestWithContext(c.Request.Context(), "POST", d.AccountBaseURL+"/token", strings.NewReader(form.Encode()))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.SetBasicAuth(creds.ClientID, creds.ClientSecret)
		resp, err := d.HTTPClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"detail": "token exchange failed: " + err.Error()})
			return
		}
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)
		if resp.StatusCode != http.StatusOK {
			c.JSON(http.StatusBadGateway, gin.H{"detail": "token exchange failed: " + string(body)})
			return
		}
		var tokens map[string]any
		if err := json.Unmarshal(body, &tokens); err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"detail": "token exchange parse failed"})
			return
		}
		access, _ := tokens["access_token"].(string)
		refresh, _ := tokens["refresh_token"].(string)
		claims := decodeJWTPayload(access)

		s := sessions.Default(c)
		s.Set("user", map[string]any{
			"display_name": firstNonEmpty(claims["name"], claims["sub"]),
			"email":        firstNonEmpty(claims["sub"], claims["email"]),
			"token":        access,
			"sso": map[string]any{
				"sid":           claims["sid"],
				"iss":           claims["iss"],
				"exp":           claims["exp"],
				"refresh_token": refresh,
			},
		})
		_ = s.Save()

		// Clear PKCE cookies now that flow is complete.
		c.SetCookie("auth_verifier", "", -1, "/", "", d.SecureCookie, true)
		c.SetCookie("auth_state", "", -1, "/", "", d.SecureCookie, true)
		c.Redirect(http.StatusSeeOther, "/docs")
	}
}

// decodeJWTPayload decodes the claims from the payload segment of a JWT
// without verifying the signature. Used only for display/session values;
// authoritative validation is done server-side by the account service.
func decodeJWTPayload(token string) map[string]any {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return map[string]any{}
	}
	seg := parts[1]
	if pad := len(seg) % 4; pad > 0 {
		seg += strings.Repeat("=", 4-pad)
	}
	raw, err := base64.URLEncoding.DecodeString(seg)
	if err != nil {
		return map[string]any{}
	}
	var out map[string]any
	_ = json.Unmarshal(raw, &out)
	return out
}

// firstNonEmpty returns the first non-empty string (or non-nil value) from values.
func firstNonEmpty(values ...any) any {
	for _, v := range values {
		if s, ok := v.(string); ok && s != "" {
			return s
		}
		if v != nil {
			return v
		}
	}
	return nil
}

// logoutWebhookHandler handles back-channel logout events from the account service.
// Verifies the HMAC-SHA256 signature and rejects stale events outside the replay window.
func logoutWebhookHandler(d SSODeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		creds, err := d.Resolver.Resolve(c.Request.Context())
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"detail": fmt.Sprintf("account-service credentials unavailable: %v", err)})
			return
		}
		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "bad body"})
			return
		}
		mac := hmac.New(sha256.New, []byte(creds.ClientSecret))
		mac.Write(body)
		expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
		presented := c.GetHeader("X-Logout-Signature")
		if !hmac.Equal([]byte(expected), []byte(presented)) {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "bad signature"})
			return
		}
		var evt map[string]any
		if err := json.Unmarshal(body, &evt); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "bad body"})
			return
		}
		iat, _ := evt["iat"].(float64)
		if absInt64(time.Now().Unix()-int64(iat)) > replayWindowS {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "stale event"})
			return
		}
		_ = context.Background() // placeholder for future session invalidation by sid
		c.Status(http.StatusNoContent)
	}
}

func absInt64(n int64) int64 {
	if n < 0 {
		return -n
	}
	return n
}
