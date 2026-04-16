package auth

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/repository"
)

// hellopro auth API response
type HelloProAuthResponse struct {
	Success     bool   `json:"success"`
	Token       string `json:"token"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

// RegisterHandlers mounts /login and /logout on the mux.
// userRepo is optional: when non-nil, each successful login upserts the user record.
func RegisterHandlers(mux *http.ServeMux, cfg Config, userRepo *repository.UserRepo) {
	mux.HandleFunc("/login", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			handleLoginPage(w, r, cfg)
		case http.MethodPost:
			handleLoginAction(w, r, cfg, userRepo)
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})

	mux.HandleFunc("/logout", func(w http.ResponseWriter, r *http.Request) {
		ClearSession(w)
		http.Redirect(w, r, "/login", http.StatusSeeOther)
	})
}

func handleLoginPage(w http.ResponseWriter, r *http.Request, cfg Config) {
	// If already authenticated, redirect to the SPA dashboard
	if session, err := GetSession(r, cfg.JWTSecret); err == nil {
		if _, err := ValidateJWT(session.Token, cfg.JWTSecret, cfg.JWTAudience); err == nil {
			http.Redirect(w, r, "/tokens", http.StatusSeeOther)
			return
		}
	}

	// In production, nginx serves the Vue SPA for GET /login.
	// This handler is only reached when accessing the Go backend directly (dev mode).
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"message":"Login page is served by the Vue SPA frontend"}`))
}

func handleLoginAction(w http.ResponseWriter, r *http.Request, cfg Config, userRepo *repository.UserRepo) {
	// Detect if this is a JSON API request (from Vue frontend) vs form submit (from Go template)
	isJSON := strings.Contains(r.Header.Get("Content-Type"), "application/json")

	var username, password string

	if isJSON {
		var body struct {
			Username string `json:"username"`
			Password string `json:"password"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte(`{"error":"Corps de requête invalide"}`))
			return
		}
		username = strings.TrimSpace(body.Username)
		password = body.Password
	} else {
		if err := r.ParseForm(); err != nil {
			http.Redirect(w, r, "/login?error="+url.QueryEscape("Erreur de formulaire"), http.StatusSeeOther)
			return
		}
		username = strings.TrimSpace(r.FormValue("username"))
		password = r.FormValue("password")
	}

	if username == "" || password == "" {
		if isJSON {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte(`{"error":"Tous les champs sont obligatoires"}`))
		} else {
			http.Redirect(w, r, "/login?error="+url.QueryEscape("Tous les champs sont obligatoires")+"&username="+url.QueryEscape(username), http.StatusSeeOther)
		}
		return
	}

	// Authenticate against hellopro.fr API
	authResp, err := AuthenticateHellopro(cfg.AuthURL, username, password)

	// Fallback: if hellopro auth fails, check env-based fallback credentials
	if (err != nil || !authResp.Success) && cfg.FallbackUser != "" {
		if username == cfg.FallbackUser && password == cfg.FallbackPass {
			log.Printf("[auth] fallback auth matched for %s", username)
			authResp = &HelloProAuthResponse{
				Success:     true,
				Email:       cfg.FallbackEmail,
				DisplayName: cfg.FallbackUser,
			}
			err = nil
		}
	}

	if err != nil {
		log.Printf("[auth] hellopro auth failed for %s: %v", username, err)
		if isJSON {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(`{"error":"Erreur d'authentification"}`))
		} else {
			http.Redirect(w, r, "/login?error="+url.QueryEscape("Erreur d'authentification")+"&username="+url.QueryEscape(username), http.StatusSeeOther)
		}
		return
	}

	if !authResp.Success {
		if isJSON {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(`{"error":"Identifiants invalides"}`))
		} else {
			http.Redirect(w, r, "/login?error="+url.QueryEscape("Login / Mot de passe invalide")+"&username="+url.QueryEscape(username), http.StatusSeeOther)
		}
		return
	}

	// Upsert user record BEFORE access check so the user exists in DB even if not allowed.
	// This lets admins see and authorize users from the UI.
	role := RoleConfigOnly
	isAllowed := true // default: allowed when no userRepo (DB disabled)
	if userRepo != nil {
		user, upsertErr := userRepo.UpsertOnLogin(authResp.Email, authResp.DisplayName)
		if upsertErr != nil {
			log.Printf("[auth] failed to upsert user on login for %s: %v", authResp.Email, upsertErr)
		} else if user != nil {
			role = user.Role
			isAllowed = user.IsAllowed
		}
	}

	// Check if user is allowed to access the UI (from DB is_allowed field)
	if !isAllowed {
		log.Printf("[auth] user %s (%s) is not allowed (is_allowed=false)", authResp.DisplayName, authResp.Email)
		if isJSON {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			w.Write([]byte(`{"error":"Accès non autorisé. Votre compte n'est pas dans la liste des utilisateurs autorisés. Contactez un administrateur."}`))
		} else {
			http.Redirect(w, r, "/login?error="+url.QueryEscape("Accès non autorisé. Contactez un administrateur.")+"&username="+url.QueryEscape(username), http.StatusSeeOther)
		}
		return
	}

	// Generate our own JWT for the session (or use the one from hellopro)
	token := authResp.Token
	if token == "" {
		// Generate a local JWT
		claims := Claims{
			Audience: cfg.JWTAudience,
			Exp:      time.Now().Add(24 * time.Hour).Unix(),
			Iat:      time.Now().Unix(),
			Name:     authResp.DisplayName,
			Email:    authResp.Email,
		}
		var signErr error
		token, signErr = SignJWT(cfg.JWTSecret, claims)
		if signErr != nil {
			log.Printf("[auth] failed to sign JWT: %v", signErr)
			if isJSON {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				w.Write([]byte(`{"error":"Erreur serveur"}`))
			} else {
				http.Redirect(w, r, "/login?error="+url.QueryEscape("Erreur serveur"), http.StatusSeeOther)
			}
			return
		}
	}

	// Set session cookie (for backward compat with Go template UI)
	if err := SetSession(w, cfg.JWTSecret, SessionData{
		DisplayName: authResp.DisplayName,
		Email:       authResp.Email,
		Token:       token,
	}, cfg.SecureCookie); err != nil {
		log.Printf("[auth] failed to set session: %v", err)
	}

	log.Printf("[auth] user %s (%s) logged in", authResp.DisplayName, authResp.Email)

	if isJSON {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"token":        token,
			"email":        authResp.Email,
			"display_name": authResp.DisplayName,
			"role":         role,
		})
	} else {
		http.Redirect(w, r, "/ui/", http.StatusSeeOther)
	}
}

func AuthenticateHellopro(authURL, username, password string) (*HelloProAuthResponse, error) {
	// Security: validate that auth URL uses HTTPS to prevent credential interception
	parsed, err := url.Parse(authURL)
	if err != nil {
		return nil, fmt.Errorf("invalid auth URL: %w", err)
	}
	if parsed.Scheme != "https" && parsed.Hostname() != "localhost" && parsed.Hostname() != "127.0.0.1" {
		return nil, fmt.Errorf("auth URL must use HTTPS (got %s)", parsed.Scheme)
	}

	data := url.Values{
		"login":    {username},
		"password": {password},
	}

	client := &http.Client{
		Timeout: 10 * time.Second,
		// Do not follow redirects — prevents MITM via redirect to attacker server
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	resp, err := client.PostForm(authURL, data)
	if err != nil {
		return nil, fmt.Errorf("auth request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		// Truncate body to avoid leaking sensitive upstream data in logs
		return nil, fmt.Errorf("auth returned status %d (body length: %d bytes)", resp.StatusCode, len(body))
	}

	var authResp HelloProAuthResponse
	if err := json.Unmarshal(body, &authResp); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}

	return &authResp, nil
}

