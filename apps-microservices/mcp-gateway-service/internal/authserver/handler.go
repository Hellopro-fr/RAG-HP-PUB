package authserver

import (
	"net/http"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

// ssoSessionFinder is the slice of *repository.SSOSessionRepo that the
// /authorize bridge needs. Defining it as an interface lets tests substitute
// an in-memory fake without spinning up GORM.
type ssoSessionFinder interface {
	FindByID(id string) (*db.SSOSession, error)
}

// AuthServer holds dependencies for the OAuth2 Authorization Server endpoints.
type AuthServer struct {
	oauth2Repo   *repository.OAuth2Repo
	authCodeRepo *repository.AuthCodeRepo
	consentRepo  *repository.ConsentRepo
	refreshRepo  *repository.RefreshRepo
	serverRepo   *repository.ServerRepo
	// ssoSessionRepo is the optional bridge into the admin SSO session store.
	// When set, GET /authorize with no mcp_session cookie but a valid gw_session
	// cookie reuses the SSO identity instead of bouncing through /sso/login.
	// Nil disables the bridge — falls through to the SSO-redirect path.
	ssoSessionRepo ssoSessionFinder
	jwtSecret      string
	publicURL      string
	authURL        string // hellopro.fr auth endpoint
	secureCookie   bool
	refreshTTL     int // refresh token lifetime in seconds
}

// AuthServerConfig holds configuration for creating an AuthServer.
type AuthServerConfig struct {
	OAuth2Repo     *repository.OAuth2Repo
	AuthCodeRepo   *repository.AuthCodeRepo
	ConsentRepo    *repository.ConsentRepo
	RefreshRepo    *repository.RefreshRepo
	ServerRepo     *repository.ServerRepo
	SSOSessionRepo ssoSessionFinder // optional, enables gw_session bridge
	JWTSecret      string
	PublicURL      string
	AuthURL        string
	SecureCookie   bool
	RefreshTTL     int
}

// NewAuthServer creates a new AuthServer.
func NewAuthServer(cfg AuthServerConfig) *AuthServer {
	return &AuthServer{
		oauth2Repo:     cfg.OAuth2Repo,
		authCodeRepo:   cfg.AuthCodeRepo,
		consentRepo:    cfg.ConsentRepo,
		refreshRepo:    cfg.RefreshRepo,
		serverRepo:     cfg.ServerRepo,
		ssoSessionRepo: cfg.SSOSessionRepo,
		jwtSecret:      cfg.JWTSecret,
		publicURL:      cfg.PublicURL,
		authURL:        cfg.AuthURL,
		secureCookie:   cfg.SecureCookie,
		refreshTTL:     cfg.RefreshTTL,
	}
}

// Register mounts all OAuth2 Authorization Server routes on the mux.
func (s *AuthServer) Register(mux *http.ServeMux) {
	mux.HandleFunc("/.well-known/oauth-authorization-server", s.HandleMetadata)
	mux.HandleFunc("/authorize", s.HandleAuthorize)
	mux.HandleFunc("/token", s.HandleToken)
	mux.HandleFunc("/register", s.HandleRegister)
}
