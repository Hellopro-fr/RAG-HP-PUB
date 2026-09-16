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

// gatewayUserFinder is the slice of *repository.UserRepo the consent screen
// needs to resolve a viewer's role. An interface keeps authserver tests free
// of GORM. nil disables the access gate — see the note on AuthServer.userRepo.
type gatewayUserFinder interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}

// AuthServer holds dependencies for the OAuth2 Authorization Server endpoints.
type AuthServer struct {
	oauth2Repo   *repository.OAuth2Repo
	authCodeRepo *repository.AuthCodeRepo
	consentRepo  *repository.ConsentRepo
	refreshRepo  *repository.RefreshRepo
	serverRepo   *repository.ServerRepo
	// userRepo (optional) resolves a consent viewer's gateway role so
	// servers carrying a min_role can be hidden from viewers below it.
	// When nil, gateway.FilterServersByGate denies every gated server —
	// fail-closed: an unwired repo hides gated servers rather than
	// exposing them.
	userRepo gatewayUserFinder
	// ssoSessionRepo is the optional bridge into the admin SSO session store.
	// When set, GET /authorize with no mcp_session cookie but a valid gw_session
	// cookie reuses the SSO identity instead of bouncing through /sso/login.
	// Nil disables the bridge — falls through to the SSO-redirect path.
	ssoSessionRepo ssoSessionFinder
	// zohoFetcher (optional) — when set, the consent screen partitions
	// servers into "Configurés"/"Non configurés" using each backend's
	// per-viewer ZohoServerState.Configured flag.
	zohoFetcher ZohoStateForUser
	// docsURL is the absolute URL surfaced in the "Non configurés"
	// section so viewers know where to learn how to wire their Zoho
	// import. Computed from GATEWAY_PUBLIC_URL + "/docs/zohocrm" at
	// boot.
	docsURL      string
	jwtSecret    string
	publicURL    string
	authURL      string // hellopro.fr auth endpoint
	secureCookie bool
	refreshTTL   int // refresh token lifetime in seconds
}

// AuthServerConfig holds configuration for creating an AuthServer.
type AuthServerConfig struct {
	OAuth2Repo     *repository.OAuth2Repo
	AuthCodeRepo   *repository.AuthCodeRepo
	ConsentRepo    *repository.ConsentRepo
	RefreshRepo    *repository.RefreshRepo
	ServerRepo     *repository.ServerRepo
	UserRepo       gatewayUserFinder // optional, enables the min_role consent gate
	SSOSessionRepo ssoSessionFinder  // optional, enables gw_session bridge
	ZohoFetcher    ZohoStateForUser  // optional, partitions consent screen per viewer
	DocsURL        string            // optional, populated when GATEWAY_PUBLIC_URL is set
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
		userRepo:       cfg.UserRepo,
		ssoSessionRepo: cfg.SSOSessionRepo,
		zohoFetcher:    cfg.ZohoFetcher,
		docsURL:        cfg.DocsURL,
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
