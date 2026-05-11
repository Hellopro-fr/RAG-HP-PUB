package sso

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type ClientCredentials struct {
	ClientID     string
	ClientSecret string
	RedirectURIs []string
}

type ResolverConfig struct {
	ServiceName    string
	AccountBaseURL string
	HTTPClient     *http.Client
}

type Resolver struct {
	cfg    ResolverConfig
	mu     sync.Mutex
	cached *ClientCredentials
}

func NewResolver(cfg ResolverConfig) *Resolver {
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 10 * time.Second}
	}
	return &Resolver{cfg: cfg}
}

func (r *Resolver) Resolve(ctx context.Context) (*ClientCredentials, error) {
	r.mu.Lock()
	if r.cached != nil {
		c := r.cached
		r.mu.Unlock()
		return c, nil
	}
	r.mu.Unlock()

	upper := strings.ToUpper(strings.ReplaceAll(r.cfg.ServiceName, "-", "_"))
	if id := os.Getenv("ACCOUNT_CLIENT_ID_" + upper); id != "" {
		if sec := os.Getenv("ACCOUNT_CLIENT_SECRET_" + upper); sec != "" {
			return r.cache(&ClientCredentials{ClientID: id, ClientSecret: sec}), nil
		}
	}
	if id := os.Getenv("ACCOUNT_CLIENT_ID"); id != "" {
		if sec := os.Getenv("ACCOUNT_CLIENT_SECRET"); sec != "" {
			return r.cache(&ClientCredentials{ClientID: id, ClientSecret: sec}), nil
		}
	}
	url := fmt.Sprintf("%s/internal/credentials/%s", strings.TrimRight(r.cfg.AccountBaseURL, "/"), r.cfg.ServiceName)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	if tok := os.Getenv("ACCOUNT_INTERNAL_TOKEN"); tok != "" {
		req.Header.Set("X-Admin-Token", tok)
	}
	resp, err := r.cfg.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("account-service /internal/credentials/%s returned %d", r.cfg.ServiceName, resp.StatusCode)
	}
	var body struct {
		ClientID     string   `json:"client_id"`
		ClientSecret string   `json:"client_secret"`
		RedirectURIs []string `json:"redirect_uris"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, err
	}
	if body.ClientID == "" || body.ClientSecret == "" {
		return nil, errors.New("account-service returned empty credentials")
	}
	return r.cache(&ClientCredentials{ClientID: body.ClientID, ClientSecret: body.ClientSecret, RedirectURIs: body.RedirectURIs}), nil
}

func (r *Resolver) cache(c *ClientCredentials) *ClientCredentials {
	r.mu.Lock()
	r.cached = c
	r.mu.Unlock()
	return c
}
