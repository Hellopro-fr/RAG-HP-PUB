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
	// If already authenticated, redirect to UI
	if session, err := GetSession(r, cfg.JWTSecret); err == nil {
		if _, err := ValidateJWT(session.Token, cfg.JWTSecret, cfg.JWTAudience); err == nil {
			http.Redirect(w, r, "/ui/", http.StatusSeeOther)
			return
		}
	}

	errorMsg := r.URL.Query().Get("error")
	username := r.URL.Query().Get("username")
	renderLoginPage(w, errorMsg, username)
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

	// Upsert user record and retrieve role for the login response.
	role := RoleConfigOnly
	if userRepo != nil {
		user, upsertErr := userRepo.UpsertOnLogin(authResp.Email, authResp.DisplayName)
		if upsertErr != nil {
			log.Printf("[auth] failed to upsert user on login for %s: %v", authResp.Email, upsertErr)
		} else if user != nil {
			role = user.Role
		}
	}

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

func renderLoginPage(w http.ResponseWriter, errorMsg, username string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("X-Frame-Options", "DENY")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("Content-Security-Policy", "frame-ancestors 'none'; default-src 'self' https://cdn.tailwindcss.com; script-src 'self' https://cdn.tailwindcss.com 'unsafe-inline'; style-src 'self' 'unsafe-inline'")

	errorHTML := ""
	if errorMsg != "" {
		errorHTML = fmt.Sprintf(`<p class="text-red-500 font-bold text-sm text-center">%s</p>`, escapeHTML(errorMsg))
	}

	usernameVal := ""
	if username != "" {
		usernameVal = fmt.Sprintf(` value="%s"`, escapeHTML(username))
	}

	html := `<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex">
    <title>Authentification - MCP Server Manager</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = { theme: { extend: { colors: {
        brand: { 50:'#f0f7ff', 100:'#e0effe', 200:'#bae0fd', 300:'#7ccbfc', 400:'#36b2f8', 500:'#0c96e9', 600:'#0078c7', 700:'#005fa1', 800:'#035185', 900:'#07446e' }
      }}}}
    </script>
    <style>
        .auth-bg { background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%); }
        .input-field:focus { border-color: #0c96e9; box-shadow: 0 0 0 3px rgba(12, 150, 233, 0.2); }
        .btn-primary { background: linear-gradient(to right, #005fa1, #0078c7); transition: all 0.3s ease; }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 20px -10px rgba(0, 120, 199, 0.6); }
    </style>
</head>
<body class="min-h-screen bg-gray-50">
    <div class="flex min-h-screen items-center justify-center p-4">
        <div class="auth-bg w-full max-w-md rounded-xl bg-white p-8 shadow-xl">
            <div class="mb-8 text-center">
                <div class="mx-auto w-12 h-12 rounded-xl bg-brand-600 flex items-center justify-center mb-4">
                    <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M12 5l7 7-7 7"/></svg>
                </div>
                <h1 class="text-2xl font-bold text-gray-800">MCP Server Manager</h1>
                <p class="mt-2 text-gray-500">Connectez-vous a votre compte</p>
            </div>

            <form class="space-y-5" method="post" action="/login" id="loginForm">
                ` + errorHTML + `
                <div>
                    <label for="username" class="block text-sm font-medium text-gray-700">Nom d'utilisateur <span class="text-red-600">*</span></label>
                    <div class="mt-1 relative">
                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
                        </div>
                        <input id="username" name="username" type="text" required
                            class="input-field block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg focus:outline-none text-sm"
                            placeholder="Votre nom d'utilisateur"` + usernameVal + `>
                    </div>
                </div>

                <div>
                    <label for="password" class="block text-sm font-medium text-gray-700">Mot de passe <span class="text-red-600">*</span></label>
                    <div class="mt-1 relative">
                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
                        </div>
                        <input id="password" name="password" type="password" required
                            class="input-field block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg focus:outline-none text-sm"
                            placeholder="Votre mot de passe">
                    </div>
                </div>

                <button type="submit" id="submitBtn"
                    class="btn-primary w-full flex justify-center items-center py-3 px-4 border border-transparent rounded-lg text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-500">
                    <span id="btnText">Se connecter</span>
                    <svg id="spinner" class="ml-2 hidden w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                </button>
            </form>
        </div>
    </div>
    <script>
        document.querySelectorAll('input').forEach(el => el.addEventListener('focus', () => {
            const err = document.querySelector('.text-red-500');
            if (err) err.classList.add('hidden');
        }));
        document.getElementById('loginForm').addEventListener('submit', function() {
            document.getElementById('btnText').textContent = 'Connexion...';
            document.getElementById('spinner').classList.remove('hidden');
            document.getElementById('submitBtn').disabled = true;
        });
    </script>
</body>
</html>`

	w.Write([]byte(html))
}

func escapeHTML(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, "\"", "&quot;")
	s = strings.ReplaceAll(s, "'", "&#39;")
	return s
}